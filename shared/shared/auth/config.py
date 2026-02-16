from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JWT_", extra="ignore")

    secret: str = "change-me"
    algorithm: str = "HS256"
    issuer: str = "docfliq-identity"
    audience: str = "docfliq-services"
