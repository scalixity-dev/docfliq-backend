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
from app.auth.router import router as auth_router
from app.profile.router import router as profile_router
from app.verification.router import router as verification_router
from app.verification.admin_router import router as verification_admin_router
from app.social_graph.router import router as social_router
from app.social_graph.admin_router import router as social_admin_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware


# ── OpenAPI metadata ──────────────────────────────────────────────────────────

_DESCRIPTION = """
## Docfliq Identity Service (MS-1)

Handles all user identity concerns for the Docfliq platform:

* **Authentication** — email/password and phone OTP login, JWT access + refresh tokens,
  session management (up to 5 active sessions per user), per-account login lockout.
* **Registration** — role-based sign-up (Doctor, Pharmacist, Student, etc.) with
  role-specific profile fields.
* **Password reset** — via 6-digit OTP (email) or 1-hour magic link.
* **Email verification** — 24-hour token link sent on registration, resendable.
* **User profiles** — view and update own profile; view other users' public profiles.
* **Professional verification** — upload documents (S3 presigned URL), admin review queue,
  approve / reject workflow, suspension and reinstatement.
* **Social graph** — unidirectional follows (Twitter-style), blocks (hides profiles + lists),
  mutes (hides feed content), user/content reports with admin review.

### Authentication
All protected endpoints require:
```
Authorization: Bearer <access_token>
```
Admin endpoints additionally require the `admin` or `super_admin` role in the token.

### Error shape
All errors return a consistent JSON envelope:
```json
{ "detail": "Human-readable message" }
```
Validation errors (`422`) return the standard Pydantic error list under `detail`.

### Rate limits
`429 Too Many Requests` is returned when a rate limit is exceeded. The response includes
a `Retry-After` header indicating when the client may retry.
"""

_TAGS_METADATA = [
    {
        "name": "auth",
        "description": (
            "Registration, login (email+password and OTP), token refresh/logout, "
            "password reset (OTP + magic link), and email verification."
        ),
    },
    {
        "name": "profile",
        "description": (
            "View and update user profiles. `GET /users/me` returns the authenticated user's "
            "full profile. `GET /users/{user_id}` returns another user's public profile "
            "(returns 404 if that user has blocked you)."
        ),
    },
    {
        "name": "verification",
        "description": (
            "Professional document verification for the authenticated user. "
            "Step 1: `POST /upload` — get a presigned S3 PUT URL. "
            "Step 2: PUT the file directly to S3. "
            "Step 3: `POST /confirm` — notify the server the upload is complete. "
            "The document enters the admin review queue."
        ),
    },
    {
        "name": "admin-verification",
        "description": (
            "**Admin only.** Manage the professional verification queue: "
            "view pending documents, download originals via presigned GET URLs, "
            "approve or reject submissions, and suspend / reinstate verified users."
        ),
    },
    {
        "name": "social-graph",
        "description": (
            "Unidirectional follows (Twitter-style), blocks, mutes, and user reports. "
            "Blocking a user removes follow edges in both directions and hides their "
            "profile and follow lists with a 404. "
            "Muting hides their content from your feed without affecting follow state."
        ),
    },
    {
        "name": "admin-social-graph",
        "description": (
            "**Admin only.** Review and action user/content reports submitted via "
            "`POST /users/{user_id}/report`."
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
    init_db(settings.identity_database_url)
    yield
    # Shutdown: close pools if needed (shared factory holds engine)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Docfliq Identity Service",
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

    # Middleware is applied in reverse-registration order (last added = outermost).
    # CORS must be outermost so ALL responses (including 429s) carry CORS headers.
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

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(verification_router, prefix="/api/v1")
    app.include_router(verification_admin_router, prefix="/api/v1")
    app.include_router(social_router, prefix="/api/v1")
    app.include_router(social_admin_router, prefix="/api/v1")

    @app.get("/health", response_model=HealthResponse, tags=["health"], include_in_schema=True)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="identity")

    return app


app = create_app()
