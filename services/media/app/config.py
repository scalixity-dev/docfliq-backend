from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> list[str]:
    """Load .env from backend root (when running from services/media) then local .env."""
    base = Path(__file__).resolve().parent.parent.parent.parent  # backend root
    return [str(base / ".env"), ".env"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    media_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/media_db"
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT (shared with identity service — used for token validation) ───────
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "docfliq-identity"
    jwt_audience: str = "docfliq-services"

    # ── AWS ───────────────────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_media: str = "docfliq-user-content-dev"

    # S3 presigned URL expiry
    s3_upload_expiry_seconds: int = 900  # 15 min for PUT uploads

    # MediaConvert
    mediaconvert_endpoint: str = ""
    mediaconvert_role_arn: str = ""
    mediaconvert_queue_arn: str = ""
    mediaconvert_output_bucket: str = ""

    # CloudFront
    cloudfront_domain: str = ""
    cloudfront_key_pair_id: str = ""
    cloudfront_private_key: str = ""  # PEM string or path

    # ── CORS ─────────────────────────────────────────────────────────────────
    env_name: str = "development"
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
