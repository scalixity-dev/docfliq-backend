import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Configure application logging so background task logs are visible
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import Settings
from app.database import init_db
from app.rate_limit import limiter
from app.asset.router import router as asset_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware


# ── OpenAPI metadata ──────────────────────────────────────────────────────────

_DESCRIPTION = """
## Docfliq Media Processing Service (MS-5)

S3-based media management for the Docfliq platform.

* **Upload** — presigned S3 PUT URLs for direct file uploads (video, image, PDF, SCORM).
* **Image processing** — in-service Pillow processing: resize, compress, WebP conversion,
  thumbnail generation (150x150, 600x600, 1200x1200), avatar crops, course thumbnails.
* **Video transcoding** — AWS MediaConvert: HLS (720p + 1080p + 4K) + MP4 download + thumbnail.
* **Secure URLs** — S3 presigned URLs for time-limited content access.
* **Status tracking** — transcode status (PENDING → PROCESSING → COMPLETED/FAILED).

### Authentication
All endpoints require:
```
Authorization: Bearer <access_token>
```
Tokens are issued by the Identity service (MS-1).

### Error shape
All errors return a consistent JSON envelope:
```json
{ "detail": "Human-readable message" }
```
"""

_TAGS_METADATA = [
    {
        "name": "media",
        "description": (
            "Upload media files, manage assets, and generate signed URLs "
            "for secure content delivery."
        ),
    },
]


# ── Health schema ─────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    service: str


# ── App factory ───────────────────────────────────────────────────────────────

def get_settings() -> Settings:
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app import task_queue

    settings = get_settings()
    init_db(settings.media_database_url)
    await task_queue.init_pool(settings.redis_url)
    yield
    await task_queue.close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Docfliq Media Processing Service",
        version="1.0.0",
        description=_DESCRIPTION,
        openapi_tags=_TAGS_METADATA,
        contact={
            "name": "Docfliq Engineering",
            "email": "engineering@docfliq.com",
        },
        license_info={
            "name": "Proprietary",
        },
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Attach rate limiter state before middleware
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Middleware (applied in reverse-registration order: last added = outermost)
    app.add_middleware(SlowAPIMiddleware)
    app.middleware("http")(request_id_middleware)
    app.middleware("http")(error_envelope_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=600,
    )

    app.include_router(asset_router, prefix="/api/v1")

    @app.get("/health", response_model=HealthResponse, tags=["health"], include_in_schema=True)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="media")

    return app


app = create_app()
