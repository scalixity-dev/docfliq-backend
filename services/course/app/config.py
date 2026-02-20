from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    course_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/course_db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    env_name: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]

    # CloudFront URL signing
    cloudfront_domain: str = ""
    cloudfront_key_pair_id: str = ""
    cloudfront_private_key_path: str = ""
    cloudfront_signed_url_expiry_secs: int = 14400  # 4 hours for paid content
    cloudfront_preview_expiry_secs: int = 3600  # 1 hour for preview content

    # S3 for certificate PDFs
    s3_bucket: str = "docfliq-media"
    s3_certificate_prefix: str = "certificates/"
    s3_region: str = "us-east-1"

    # Certificate generation
    certificate_signing_secret: str = "change-me-certificate-secret"
    certificate_base_url: str = "https://docfliq.com/certificates"
