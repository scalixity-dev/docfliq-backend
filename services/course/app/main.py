from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import init_db
from app.lms.router import router as lms_router
from app.assessment.router import router as assessment_router
from app.certificates.router import router as certificates_router
from app.player.router import router as player_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware


def get_settings() -> Settings:
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.course_database_url)

    # Redis pool
    app.state.redis = aioredis.from_url(
        settings.redis_url, decode_responses=True,
    )

    yield

    # Shutdown
    await app.state.redis.aclose()


SWAGGER_DESCRIPTION = """\
## MS-3: Course & LMS Service

Owns complete learning management: courses, catalog, enrollment,
video playback with resume, assessments, progress tracking,
SCORM wrapper, and certificate generation with QR verification.

### Domain Tags

| Tag | Description |
|-----|-------------|
| **LMS** | Course, module, lesson CRUD + enrollment + progress tracking |
| **Assessment** | Quiz management (MCQ/MSQ) + timed attempts + grading |
| **Player** | Video/document playback, signed URLs, heartbeat, SCORM, weighted progress |
| **Certificates** | Certificate generation + public QR verification |

### Authentication

All endpoints (except health check and certificate verification)
require a valid JWT Bearer token in the `Authorization` header.
Token structure: `{"sub": "<user_uuid>", "email": "...", "roles": [...]}`.

### Enrollment Flows

- **Free**: `POST /api/v1/lms/courses/{id}/enroll` — instant access
- **Paid**: `POST /api/v1/lms/courses/{id}/enroll/paid` — requires `payment_id` from MS-6

### Status Transitions

```
Course:     DRAFT → PUBLISHED → ARCHIVED
Enrollment: IN_PROGRESS → COMPLETED | DROPPED
Lesson:     NOT_STARTED → IN_PROGRESS → COMPLETED
```
"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Docfliq Course & LMS",
        version="0.1.0",
        description=SWAGGER_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=600,
    )
    app.middleware("http")(request_id_middleware)
    app.middleware("http")(error_envelope_middleware)

    app.include_router(lms_router, prefix="/api/v1")
    app.include_router(assessment_router, prefix="/api/v1")
    app.include_router(player_router, prefix="/api/v1")
    app.include_router(certificates_router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        return {"status": "ok", "service": "course"}

    return app


app = create_app()
