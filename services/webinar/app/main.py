from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.live_streaming.router import router as live_router
from app.engagement.router import router as engagement_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware


def get_settings() -> Settings:
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Docfliq Webinar",
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

    app.include_router(live_router, prefix="/api/v1")
    app.include_router(engagement_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "webinar"}

    return app


app = create_app()
