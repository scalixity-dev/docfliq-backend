from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import Settings
from app.database import init_db
from app.rate_limit import limiter
from app.asset.router import router as asset_router
from app.asset.router import callback_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware


# ── OpenAPI metadata ──────────────────────────────────────────────────────────

_DESCRIPTION = """
## Docfliq Media Processing Service (MS-5)

Event-driven media processing for the Docfliq platform.

* **Upload** — presigned S3 PUT URLs for direct file uploads (video, image, PDF, SCORM).
* **Video transcoding** — AWS MediaConvert produces HLS (720p + 1080p + 4K) + MP4 download.
* **Image processing** — Lambda + Pillow: resize, compress, WebP conversion,
  thumbnail generation (150x150, 600x600, 1200x1200), avatar crops, course thumbnails.
* **Secure URLs** — CloudFront signed URLs for paid content; S3 presigned URLs for uploads.
* **Status tracking** — real-time transcode status (PENDING → PROCESSING → COMPLETED/FAILED).

### Authentication
All user-facing endpoints require:
```
Authorization: Bearer <access_token>
```
Tokens are issued by the Identity service (MS-1).

### Internal callbacks
Lambda functions call `/api/v1/internal/media/callback/*` endpoints
to report processing results.

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
    {
        "name": "internal",
        "description": (
            "Internal endpoints called by Lambda functions to report "
            "processing results. Not for external use."
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
    settings = get_settings()
    init_db(settings.media_database_url)
    yield


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
    app.include_router(callback_router, prefix="/api/v1")

    @app.get("/health", response_model=HealthResponse, tags=["health"], include_in_schema=True)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="media")

    return app


app = create_app()
