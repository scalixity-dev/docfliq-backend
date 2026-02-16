from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.auth.controller import login as login_controller, register as register_controller
from app.config import Settings
from app.database import get_db


router = APIRouter(prefix="/auth", tags=["auth"])


def get_settings() -> Settings:
    return Settings()


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    return await register_controller(session, body, settings)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    return await login_controller(session, body, settings)
