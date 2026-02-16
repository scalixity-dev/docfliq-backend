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
        title="Docfliq Content",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
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

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "content"}

    return app


app = create_app()
