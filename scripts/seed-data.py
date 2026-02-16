#!/usr/bin/env python3
"""
Seed dev databases with minimal data.
Run from repo root: python scripts/seed-data.py
Uses IDENTITY_DATABASE_URL (and others) from env or .env.
"""
import os
import sys
from pathlib import Path

# Repo root on path for shared and service imports
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services" / "identity"))

def seed_identity() -> None:
    url = os.environ.get(
        "IDENTITY_DATABASE_URL",
        "postgresql+asyncpg://docfliq:changeme@localhost:5432/identity_db",
    )
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

        engine = create_async_engine(url, echo=False)
        async_session = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async def _run() -> None:
            from passlib.context import CryptContext
            import uuid
            ctx = CryptContext(schemes=["argon2"], deprecated="auto")
            async with async_session() as session:
                await session.execute(
                    text("""
                        INSERT INTO users (id, email, password_hash, roles, is_active, created_at, updated_at)
                        VALUES (:id, :email, :pw, :roles, true, NOW(), NOW())
                        ON CONFLICT (email) DO NOTHING
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "email": "seed@docfliq.local",
                        "pw": ctx.hash("seedpassword"),
                        "roles": ["user"],
                    },
                )
                await session.commit()

        import asyncio
        asyncio.run(_run())
        print("Identity: seeded seed@docfliq.local")
    except Exception as e:
        print(f"Identity seed skip or error: {e}", file=sys.stderr)


def main() -> None:
    seed_identity()
    print("Seed done.")


if __name__ == "__main__":
    main()
