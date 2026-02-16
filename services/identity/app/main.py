from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import init_db
from app.auth.router import router as auth_router
from app.profile.router import router as profile_router
from app.verification.router import router as verification_router
from app.social_graph.router import router as social_router
from shared.middleware.request_id import request_id_middleware
from shared.middleware.error_handler import error_envelope_middleware


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
        title="Docfliq Identity",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    # CORS first (per FastAPI rule)
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

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(verification_router, prefix="/api/v1")
    app.include_router(social_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "identity"}

    return app


app = create_app()
