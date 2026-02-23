from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> list[str]:
    """Load .env from backend root so JWT_* vars are always available."""
    base = Path(__file__).resolve().parents[3]  # shared/shared/auth/ → backend root
    return [str(base / ".env"), ".env"]


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret: str = "change-me"
    algorithm: str = "HS256"
    issuer: str = "docfliq-identity"
    audience: str = "docfliq-services"
