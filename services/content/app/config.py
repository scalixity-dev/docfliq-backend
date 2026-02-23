import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> list[str]:
    """Load .env from backend root (when running from services/content) then local .env."""
    base = Path(__file__).resolve().parent.parent.parent.parent  # backend root
    return [str(base / ".env"), ".env"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    content_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/content_db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "docfliq-identity"
    jwt_audience: str = "docfliq-services"
    env_name: str = "development"
    cors_origins: str = "http://localhost:3000"

    # OpenSearch (Amazon OpenSearch Service or self-hosted)
    opensearch_url: str = "http://localhost:9200"
    opensearch_enabled: bool = False
    opensearch_index_prefix: str = "docfliq"

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(o).strip() for o in parsed if str(o).strip()]
            except (json.JSONDecodeError, ValueError):
                pass
        return [x.strip() for x in raw.split(",") if x.strip()]
