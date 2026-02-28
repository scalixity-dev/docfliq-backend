"""
ARQ worker — media processing tasks.

Runs as a SEPARATE process from the FastAPI API server.
Consumes jobs from Redis and processes images/videos independently.

Start:  arq app.worker.WorkerSettings
Scale:  run N instances for N× throughput (each process is independent).

Architecture:
  API process:  confirm_upload → enqueue job → return 200 immediately
  Worker(s):    pick up job → download from S3 → process → upload → update DB
  Redis:        job queue, no data lost if worker restarts (auto-retry)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.config import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger("media.worker")

# ── Startup / shutdown hooks ────────────────────────────────────────────────
# ARQ calls these once per worker process. We init DB + settings here so each
# worker has its own connection pool — completely independent from the API.


async def startup(ctx: dict[str, Any]) -> None:
    """Called once when the worker process starts."""
    settings = Settings()
    ctx["settings"] = settings

    # Init DB pool for this worker process
    from app.database import init_db
    init_db(settings.media_database_url)

    logger.info("Worker started — DB pool initialized")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Called once when the worker process stops."""
    logger.info("Worker shutting down")


# ── Image processing task ──────────────────────────────────────────────────

async def process_image(ctx: dict[str, Any], asset_id: str, s3_key: str) -> str:
    """
    Download image from S3, process with Pillow (resize, compress, WebP),
    upload variants, and update DB status.

    Each invocation is fully independent — safe to run hundreds in parallel
    across multiple worker processes.
    """
    from app.asset import service
    from app.asset.constants import TranscodeStatus
    from app.database import get_session_factory
    from app.s3 import download_object, upload_object

    settings: Settings = ctx["settings"]
    uid = uuid.UUID(asset_id)

    try:
        # 1. Download original image
        image_data = await download_object(s3_key, settings)

        # 2. Process with Pillow (CPU-bound → offload to thread)
        loop = asyncio.get_running_loop()
        variants = await loop.run_in_executor(
            None, lambda: service.process_image_sync(image_data),
        )

        # 3. Upload each processed variant to S3
        processed_url = None
        thumbnail_url = None
        for size_name, webp_bytes in variants.items():
            out_key = service.build_processed_key(s3_key, size_name)
            s3_url = await upload_object(out_key, webp_bytes, "image/webp", settings)
            if size_name == "large":
                processed_url = s3_url
            elif size_name == "thumbnail":
                thumbnail_url = s3_url

        # 4. Update DB status
        factory = get_session_factory()
        async with factory() as session:
            await service.update_transcode_status(
                session,
                uid,
                status=TranscodeStatus.COMPLETED,
                processed_url=processed_url,
                thumbnail_url=thumbnail_url,
            )
            await session.commit()

        logger.info("Image processing completed for asset %s", asset_id)
        return "ok"

    except Exception:
        logger.exception("Image processing failed for asset %s", asset_id)
        try:
            factory = get_session_factory()
            async with factory() as session:
                await service.update_transcode_status(
                    session,
                    uid,
                    status=TranscodeStatus.FAILED,
                    error_message="Image processing failed",
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to update error status for asset %s", asset_id)
        raise  # Let ARQ know the job failed (for retry logic)


# ── Video processing task ──────────────────────────────────────────────────

async def process_video(ctx: dict[str, Any], asset_id: str, s3_key: str) -> str:
    """
    Submit MediaConvert job and poll until done.
    Produces HLS (720p + 1080p + 4K) + MP4 download + thumbnail.
    """
    from app.asset import service
    from app.asset.constants import TranscodeStatus
    from app.database import get_session_factory
    from app.mediaconvert import poll_job_until_done, submit_transcode_job

    settings: Settings = ctx["settings"]
    uid = uuid.UUID(asset_id)

    try:
        # 1. Submit MediaConvert job
        job_id = await submit_transcode_job(s3_key, settings)

        # 2. Store job_id in DB
        factory = get_session_factory()
        async with factory() as session:
            await service.update_transcode_status(
                session,
                uid,
                status=TranscodeStatus.PROCESSING,
                mediaconvert_job_id=job_id,
            )
            await session.commit()

        logger.info("MediaConvert job %s submitted for asset %s", job_id, asset_id)

        # 3. Poll until done
        result = await poll_job_until_done(job_id, settings)

        # 4. Update DB with result
        async with factory() as session:
            if result["status"] == "COMPLETED":
                await service.update_transcode_status(
                    session,
                    uid,
                    status=TranscodeStatus.COMPLETED,
                    processed_url=result.get("processed_url"),
                    hls_url=result.get("hls_url"),
                    thumbnail_url=result.get("thumbnail_url"),
                    duration_secs=result.get("duration_secs"),
                    resolution=result.get("resolution"),
                )
                logger.info("Video transcoding completed for asset %s", asset_id)
            else:
                await service.update_transcode_status(
                    session,
                    uid,
                    status=TranscodeStatus.FAILED,
                    error_message=result.get("error_message", "Transcoding failed"),
                )
                logger.error(
                    "Video transcoding failed for asset %s: %s",
                    asset_id,
                    result.get("error_message"),
                )
            await session.commit()

        return "ok"

    except Exception:
        logger.exception("Video processing failed for asset %s", asset_id)
        try:
            factory = get_session_factory()
            async with factory() as session:
                await service.update_transcode_status(
                    session,
                    uid,
                    status=TranscodeStatus.FAILED,
                    error_message="Failed to submit or poll MediaConvert job",
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to update error status for asset %s", asset_id)
        raise


# ── ARQ worker configuration ──────────────────────────────────────────────

def _redis_settings() -> RedisSettings:
    """Parse redis_url from Settings into ARQ RedisSettings."""
    settings = Settings()
    url = settings.redis_url  # e.g. redis://localhost:6379/0
    # arq RedisSettings accepts host/port/database
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


class WorkerSettings:
    """ARQ reads this class to configure the worker process."""
    functions = [process_image, process_video]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    # Each worker process handles up to 20 concurrent jobs.
    # Run 2-4 worker processes for 40-80 parallel tasks.
    max_jobs = 20
    # Retry failed jobs up to 3 times with exponential backoff
    max_tries = 3
    # Job timeout: images=5min, videos=30min (use the longer one)
    job_timeout = 1800
    # Keep results for 1 hour (for debugging)
    keep_result = 3600
    # Queue name — separate from other services
    queue_name = "media:tasks"
