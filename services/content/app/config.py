import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    content_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/content_db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    env_name: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]

    # OpenSearch (Amazon OpenSearch Service or self-hosted)
    opensearch_url: str = "http://localhost:9200"
    opensearch_enabled: bool = False
    opensearch_index_prefix: str = "docfliq"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]
