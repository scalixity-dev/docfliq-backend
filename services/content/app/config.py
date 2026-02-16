from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    content_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/content_db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    env_name: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]
