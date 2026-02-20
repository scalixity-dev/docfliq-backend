from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> list[str]:
    """Load .env from backend root (when running from services/identity) then local .env."""
    base = Path(__file__).resolve().parent.parent.parent.parent  # backend root
    return [str(base / ".env"), ".env"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    identity_database_url: str = "postgresql+asyncpg://docfliq:changeme@localhost:5432/identity_db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "docfliq-identity"
    jwt_audience: str = "docfliq-services"
    jwt_expire_seconds: int = 900              # 15 minutes (access token)
    jwt_refresh_expire_seconds: int = 604_800  # 7 days (refresh token)
    env_name: str = "development"
    # Comma-separated in .env (e.g. CORS_ORIGINS=http://localhost:3000,http://localhost:8080)
    cors_origins: str = "http://localhost:3000"

    # ── SMTP (primary email provider — CiNet / Postal) ─────────────────────────
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "DOCFLIQ"
    smtp_start_tls: bool = True  # upgrade to TLS via STARTTLS (port 25/587)

    # ── Brevo (fallback email provider) ──────────────────────────────────────────
    brevo_api_key: str = ""
    brevo_from_email: str = "noreply@docfliq.com"
    brevo_from_name: str = "DOCFLIQ"
    # Admin inbox — receives a notification whenever a new verification doc is submitted.
    # Leave empty to disable admin notifications (e.g. in development).
    admin_notification_email: str = ""

    # ── Twilio Verify (OTP via SMS) ─────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""

    # ── App URLs ───────────────────────────────────────────────────────────────
    # Used to build email verification links. No trailing slash.
    app_base_url: str = "http://localhost:3000"

    # ── AWS / S3 ───────────────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket: str = "docfliq-user-content-prod"
    s3_presigned_expiry_seconds: int = 900  # 15 min for PUT uploads

    @property
    def cors_origins_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
