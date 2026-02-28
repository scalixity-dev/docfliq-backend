"""Pagination utilities for the course service.

Provides offset-based pagination (suitable for course catalogs)
and cursor-based pagination (suitable for enrollment lists).
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Offset pagination
# ---------------------------------------------------------------------------


class OffsetParams(BaseModel):
    """Query parameters for offset pagination."""

    limit: int = Field(default=20, ge=1, le=100, description="Items per page.")
    offset: int = Field(default=0, ge=0, description="Number of items to skip.")


class OffsetPage[T](BaseModel):
    """Offset-paginated response envelope."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Cursor pagination
# ---------------------------------------------------------------------------


def encode_cursor(created_at: datetime, record_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{record_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), UUID(id_str)


class CursorPage[T](BaseModel):
    """Cursor-paginated response envelope."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
