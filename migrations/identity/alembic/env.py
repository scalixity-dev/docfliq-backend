import asyncio
import os
import sys
from pathlib import Path

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Path setup ────────────────────────────────────────────────────────────────
# env.py lives at: docfliq-backend/migrations/identity/alembic/env.py
#   parents[0] = .../alembic/
#   parents[1] = .../identity/
#   parents[2] = .../migrations/
#   parents[3] = docfliq-backend/   ← repo root
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))                          # makes `shared` importable
sys.path.insert(0, str(repo_root / "services" / "identity"))  # makes `app` importable

# ── ALL model modules must be imported so Alembic's autogenerate detects them ─
from app.auth.models import AuthSession, OTPRequest, PasswordResetToken, User  # noqa: E402
from app.verification.models import UserVerification  # noqa: E402
from app.social_graph.models import Block, Follow, Mute, Report  # noqa: E402
from shared.database.postgres import Base  # noqa: E402

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer the env var so docker-compose and CI can override without touching ini
url = os.environ.get("IDENTITY_DATABASE_URL") or config.get_main_option(
    "sqlalchemy.url"
)
# Escape '%' as '%%' for configparser interpolation (URL-encoded passwords)
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

target_metadata = Base.metadata


# ── Offline mode ──────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (useful for review/dry-run)."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (async) ───────────────────────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
