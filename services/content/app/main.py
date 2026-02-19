from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import init_db
from app.cms.router import router as cms_router
from app.feed.router import router as feed_router
from app.search.router import router as search_router
from app.interactions.router import router as interactions_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware

# Swagger tag groups displayed in the OpenAPI docs sidebar
_OPENAPI_TAGS = [
    {
        "name": "CMS",
        "description": (
            "Content management: create, edit, publish, version, and delete posts and channels. "
            "Includes full edit history and version restoration."
        ),
    },
    {
        "name": "Feed",
        "description": (
            "Read-optimised content feeds. Returns PUBLISHED and EDITED posts. "
            "Supports home feed, user profile feeds, and channel feeds."
        ),
    },
    {
        "name": "Search",
        "description": (
            "Full-text search over published posts (PostgreSQL GIN index on title + body). "
            "Supports tag filtering, content type filtering, and channel scoping. "
            "Also provides channel search by name/description."
        ),
    },
    {
        "name": "Interactions",
        "description": (
            "Social interactions: likes, comments (2-level threading), bookmarks, "
            "internal reposts, external share tracking, and moderation reports. "
            "Comment rate limit: 5/min. Posts auto-hidden at 5 open reports."
        ),
    },
    {
        "name": "Health",
        "description": "Liveness and readiness probes.",
    },
]


def get_settings() -> Settings:
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.content_database_url)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Docfliq Content Service",
        description=(
            "Microservice owning all social content, post lifecycle management, "
            "social interactions, search/discovery, and channel management. "
            "Read-heaviest service — designed for 3,000–5,000 feed reads/sec."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=_OPENAPI_TAGS,
        lifespan=lifespan,
    )

    # CORS must be registered first (runs last in middleware stack)
    # so that preflight OPTIONS requests get CORS headers before any auth check.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=600,
    )
    app.middleware("http")(request_id_middleware)
    app.middleware("http")(error_envelope_middleware)

    app.include_router(cms_router, prefix="/api/v1")
    app.include_router(feed_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(interactions_router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        """Lightweight liveness probe. Does not hit the database."""
        return {"status": "ok", "service": "content"}

    return app


app = create_app()
