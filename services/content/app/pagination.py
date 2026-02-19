"""Shared pagination utilities for list and feed endpoints.

Two pagination strategies:
  - CursorPage: keyset/cursor-based for feed and interaction lists (no offset degradation)
  - OffsetPage: traditional offset for search (bounded result sets, user-initiated queries)
"""

import base64
import math
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """Cursor-based paginated response.

    `next_cursor` is an opaque string encoding the last item's (created_at, id).
    Pass it as the `cursor` query parameter to fetch the next page.
    """

    items: list[T]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for the next page. Null when no more pages.",
    )
    has_more: bool = Field(description="True when additional pages exist.")


class OffsetPage(BaseModel, Generic[T]):
    """Offset-based paginated response for search endpoints."""

    items: list[T]
    total: int = Field(description="Total number of matching records.")
    page: int = Field(description="Current page number (1-indexed).")
    page_size: int = Field(description="Number of items per page.")
    pages: int = Field(description="Total number of pages.")

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "OffsetPage[T]":
        pages = max(1, math.ceil(total / page_size)) if total else 1
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


def encode_cursor(dt: datetime, uid: UUID) -> str:
    """Encode a (created_at, id) pair into a URL-safe base64 cursor string."""
    raw = f"{dt.isoformat()}|{uid}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode a cursor string back to (created_at, id).

    Raises ValueError on malformed cursors — callers should catch and return 422.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        dt_str, uid_str = raw.split("|", 1)
        return datetime.fromisoformat(dt_str), UUID(uid_str)
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {exc}") from exc
