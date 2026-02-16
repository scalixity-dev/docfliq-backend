from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    identity_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/identity_db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "docfliq-identity"
    jwt_audience: str = "docfliq-services"
    jwt_expire_seconds: int = 3600
    env_name: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]
