"""SCORM package import — background task that extracts a SCORM zip,
parses imsmanifest.xml, and auto-generates modules + lessons.

Designed to run via FastAPI ``BackgroundTasks``.
"""

from __future__ import annotations

import io
import logging
import zipfile
from uuid import UUID

import boto3
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exceptions import ScormImportError
from app.models.course import Course
from app.models.course_module import CourseModule
from app.models.enums import LessonType, ScormImportStatus
from app.models.lesson import Lesson
from app.scorm_import.parser import ScormItem, parse_manifest

logger = logging.getLogger(__name__)


async def import_scorm_package(
    session_factory: async_sessionmaker[AsyncSession],
    course_id: UUID,
    s3_bucket: str,
    s3_key: str,
    s3_extract_prefix: str,
    *,
    aws_region: str = "ap-south-1",
) -> None:
    """Background task: download SCORM zip from S3, parse, create modules/lessons.

    Updates ``course.scorm_import_status`` throughout the process.
    """
    async with session_factory() as db:
        try:
            course = await db.get(Course, course_id)
            if course is None:
                logger.error("SCORM import: course %s not found", course_id)
                return

            course.scorm_import_status = ScormImportStatus.PROCESSING
            await db.flush()
            await db.commit()

            # Download zip from S3
            s3 = boto3.client("s3", region_name=aws_region)
            response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            zip_bytes = response["Body"].read()

            if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
                raise ScormImportError("Uploaded file is not a valid ZIP archive.")

            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Find imsmanifest.xml
                manifest_path = None
                for name in zf.namelist():
                    if name.lower().endswith("imsmanifest.xml"):
                        manifest_path = name
                        break

                if manifest_path is None:
                    raise ScormImportError("imsmanifest.xml not found in SCORM package.")

                manifest_xml = zf.read(manifest_path).decode("utf-8")

                # Extract all files to S3 under the prefix
                for file_info in zf.infolist():
                    if file_info.is_dir():
                        continue
                    file_data = zf.read(file_info.filename)
                    dest_key = f"{s3_extract_prefix}/{file_info.filename}"
                    s3.put_object(
                        Bucket=s3_bucket,
                        Key=dest_key,
                        Body=file_data,
                        ContentType=_guess_content_type(file_info.filename),
                    )

            # Parse manifest
            manifest = parse_manifest(manifest_xml)

            # Create modules and lessons from organizations
            if manifest.organizations:
                org = manifest.organizations[0]  # Use default/first organization
                for mod_idx, item in enumerate(org.items):
                    await _create_module_from_item(
                        db, course_id, item, s3_extract_prefix,
                        module_sort=mod_idx,
                    )
            elif manifest.entry_point:
                # No organization structure — create a single module with one SCORM lesson
                module = CourseModule(
                    course_id=course_id,
                    title="SCORM Content",
                    sort_order=0,
                )
                db.add(module)
                await db.flush()

                lesson = Lesson(
                    module_id=module.module_id,
                    title="SCORM Lesson",
                    lesson_type=LessonType.SCORM,
                    scorm_entry_url=f"{s3_extract_prefix}/{manifest.entry_point}",
                    sort_order=0,
                )
                db.add(lesson)
                await db.flush()

            course.scorm_import_status = ScormImportStatus.COMPLETED
            if manifest.entry_point:
                course.scorm_import_error = None
            await db.commit()

            logger.info("SCORM import completed for course %s", course_id)

        except ScormImportError as exc:
            await db.rollback()
            async with session_factory() as db2:
                course2 = await db2.get(Course, course_id)
                if course2:
                    course2.scorm_import_status = ScormImportStatus.FAILED
                    course2.scorm_import_error = str(exc)
                    await db2.commit()
            logger.error("SCORM import failed for course %s: %s", course_id, exc)

        except Exception as exc:
            await db.rollback()
            async with session_factory() as db2:
                course2 = await db2.get(Course, course_id)
                if course2:
                    course2.scorm_import_status = ScormImportStatus.FAILED
                    course2.scorm_import_error = f"Unexpected error: {exc}"
                    await db2.commit()
            logger.exception("SCORM import unexpected error for course %s", course_id)


async def _create_module_from_item(
    db: AsyncSession,
    course_id: UUID,
    item: ScormItem,
    s3_prefix: str,
    *,
    module_sort: int,
) -> None:
    """Create a module from a top-level SCORM item. Nested items become lessons."""
    module = CourseModule(
        course_id=course_id,
        title=item.title,
        sort_order=module_sort,
    )
    db.add(module)
    await db.flush()

    if item.children:
        for lesson_idx, child in enumerate(item.children):
            _add_lesson(db, module.module_id, child, s3_prefix, sort_order=lesson_idx)
    elif item.resource_href:
        # Single SCO — treat as one lesson
        lesson = Lesson(
            module_id=module.module_id,
            title=item.title,
            lesson_type=LessonType.SCORM,
            scorm_entry_url=f"{s3_prefix}/{item.resource_href}",
            sort_order=0,
        )
        db.add(lesson)

    await db.flush()


def _add_lesson(
    db: AsyncSession,
    module_id: UUID,
    item: ScormItem,
    s3_prefix: str,
    *,
    sort_order: int,
) -> None:
    """Add a SCORM lesson from a manifest item."""
    scorm_url = f"{s3_prefix}/{item.resource_href}" if item.resource_href else None
    lesson = Lesson(
        module_id=module_id,
        title=item.title,
        lesson_type=LessonType.SCORM,
        scorm_entry_url=scorm_url,
        sort_order=sort_order,
    )
    db.add(lesson)


def _guess_content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapping = {
        "html": "text/html",
        "htm": "text/html",
        "js": "application/javascript",
        "css": "text/css",
        "json": "application/json",
        "xml": "application/xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
        "mp4": "video/mp4",
        "mp3": "audio/mpeg",
        "pdf": "application/pdf",
        "swf": "application/x-shockwave-flash",
    }
    return mapping.get(ext, "application/octet-stream")
