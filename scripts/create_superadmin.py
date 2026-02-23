#!/usr/bin/env python3
"""
Create a super_admin account for the Docfliq admin panel.

Reads credentials from .env:
    ADMIN_EMAIL      — admin account email (required)
    ADMIN_PASSWORD   — admin account password (required)
    ADMIN_NAME       — display name (optional, defaults to "Super Admin")

Usage:
    cd docfliq-backend
    python -m scripts.create_superadmin
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add backend root to path so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "identity"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.constants import UserRole
from app.auth.models import User
from app.auth.utils import hash_password
from shared.constants import Role


async def main() -> None:
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password:
        print("Error: ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env")
        sys.exit(1)
    full_name = os.getenv("ADMIN_NAME", "Super Admin")
    db_url = os.environ["IDENTITY_DATABASE_URL"]

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            print(f"User {email} already exists (id={existing.id}).")
            if Role.SUPER_ADMIN.value not in existing.roles:
                existing.roles = list(set(existing.roles) | {Role.SUPER_ADMIN.value, Role.ADMIN.value})
                await session.flush()
                await session.commit()
                print("  -> Upgraded to super_admin.")
            else:
                print("  -> Already a super_admin. Nothing to do.")
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole.ADMIN,
            roles=[Role.SUPER_ADMIN.value, Role.ADMIN.value],
            email_verified=True,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Super admin created: {email} (id={user.id})")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
