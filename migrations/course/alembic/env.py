import asyncio
import os
import sys
from pathlib import Path

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# parents: [0]=alembic/  [1]=course/  [2]=migrations/  [3]=repo_root/
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services" / "course"))

from shared.database.postgres import Base  # noqa: E402

# Import all models so Alembic autogenerate can detect them
import app.models  # noqa: E402, F401

# Tables that belong to the course service — filter out models from other services
# that share the same Base.
COURSE_TABLES = frozenset({
    "courses",
    "course_modules",
    "lessons",
    "quizzes",
    "enrollments",
    "lesson_progress",
    "certificates",
})


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in COURSE_TABLES
    return True


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("COURSE_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
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
