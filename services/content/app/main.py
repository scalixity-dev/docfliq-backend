from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import init_db
from app.cms.router import router as cms_router
from app.experiments.router import router as experiments_router
from app.feed.router import router as feed_router
from app.interactions.router import router as interactions_router
from app.notifications.router import router as notifications_router
from app.notifications.internal_router import router as notifications_internal_router
from app.search.router import router as search_router
from shared.middleware.error_handler import error_envelope_middleware
from shared.middleware.request_id import request_id_middleware

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
        "name": "Experiments",
        "description": (
            "Cohort management and A/B experimentation for feed algorithm weights. "
            "Cohorts define user segments with custom feed scoring. "
            "Experiments split cohort traffic across variants with different algorithm configs. "
            "Variant assignment is deterministic (SHA-256 hash) — no server-side storage. "
            "Results include 95% Wilson CI for CTR and normal-approximation CI for session metrics."
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
    redis_client = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    app.state.redis = redis_client

    # OpenSearch client (optional — disabled when opensearch_enabled=False)
    app.state.opensearch = None
    if settings.opensearch_enabled:
        from opensearchpy import AsyncOpenSearch
        os_client = AsyncOpenSearch(
            hosts=[settings.opensearch_url],
            use_ssl=settings.opensearch_url.startswith("https"),
            verify_certs=False,
            http_compress=True,
        )
        app.state.opensearch = os_client

    yield

    await redis_client.aclose()
    if app.state.opensearch is not None:
        await app.state.opensearch.close()


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
        allow_origins=settings.cors_origins_list,
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
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(notifications_internal_router, prefix="/api/v1")
    app.include_router(experiments_router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        """Lightweight liveness probe. Does not hit the database."""
        return {"status": "ok", "service": "content"}

    return app


app = create_app()
