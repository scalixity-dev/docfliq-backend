import asyncio
import os
import sys
from pathlib import Path

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# parents: [0]=alembic/  [1]=content/  [2]=migrations/  [3]=repo_root/
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services" / "content"))

from shared.database.postgres import Base  # noqa: E402
import app.models  # noqa: E402, F401 — registers all ORM models with Base.metadata

# Tables that belong to the content service — filter out models from other services
# that share the same Base.
CONTENT_TABLES = frozenset({
    "posts",
    "post_versions",
    "comments",
    "likes",
    "bookmarks",
    "shares",
    "reports",
    "channels",
    "editor_picks",
    "cohorts",
    "ab_experiments",
    "experiment_events",
    "notifications",
})


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in CONTENT_TABLES
    return True


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("CONTENT_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
# Escape % for ConfigParser interpolation (URL-encoded passwords contain %)
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
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
