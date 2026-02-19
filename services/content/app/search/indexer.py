"""Post/Channel indexing utilities for OpenSearch.

Two entry points:
1. sync_post_to_opensearch(post, client, index_prefix)
   — async function called as a FastAPI BackgroundTask after publish/edit.
2. sync_channel_to_opensearch(channel, client, index_prefix)
   — same pattern for channels (indexed as content_type=CHANNEL).

Celery task stubs are included for future async background processing.
When opensearch_enabled=False, the client is None and all functions are no-ops.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_post_document(post) -> dict[str, Any]:
    """Serialize a Post ORM object to an OpenSearch content document."""
    body = getattr(post, "body", None) or ""
    return {
        "content_id":       str(post.post_id),
        "content_type":     post.content_type.value if hasattr(post.content_type, "value") else str(post.content_type),
        "title":            post.title or "",
        "body_snippet":     body[:500],
        "specialty_tags":   post.specialty_tags or [],
        "author_id":        str(post.author_id),
        "pricing_type":     None,   # Posts are always free
        "duration_mins":    None,
        "created_at":       post.created_at.isoformat() if post.created_at else None,
        "popularity_score": float(
            (post.like_count or 0)
            + (post.comment_count or 0) * 2
            + (post.share_count or 0) * 3
        ),
    }


def _build_channel_document(channel) -> dict[str, Any]:
    """Serialize a Channel ORM object to an OpenSearch content document."""
    desc = getattr(channel, "description", None) or ""
    return {
        "content_id":       str(channel.channel_id),
        "content_type":     "CHANNEL",
        "title":            channel.name or "",
        "body_snippet":     desc[:500],
        "specialty_tags":   [],
        "author_id":        str(channel.owner_id) if hasattr(channel, "owner_id") else "",
        "pricing_type":     None,
        "duration_mins":    None,
        "created_at":       channel.created_at.isoformat() if channel.created_at else None,
        "popularity_score": 0.0,
    }


async def sync_post_to_opensearch(post, client, index_prefix: str) -> None:
    """Index or update a post document in OpenSearch.

    Called as a FastAPI BackgroundTask — failures are logged but never raised
    so they don't affect the API response.
    """
    if client is None:
        return
    try:
        doc = _build_post_document(post)
        await client.index(
            index=f"{index_prefix}_content",
            id=str(post.post_id),
            body=doc,
        )
    except Exception as exc:
        logger.warning("OpenSearch post indexing failed for %s: %s", post.post_id, exc)


async def delete_post_from_opensearch(post_id, client, index_prefix: str) -> None:
    """Remove a post document from the content index (called on soft-delete)."""
    if client is None:
        return
    try:
        await client.delete(
            index=f"{index_prefix}_content",
            id=str(post_id),
            ignore=404,
        )
    except Exception as exc:
        logger.warning("OpenSearch post delete failed for %s: %s", post_id, exc)


async def sync_channel_to_opensearch(channel, client, index_prefix: str) -> None:
    """Index or update a channel document in OpenSearch."""
    if client is None:
        return
    try:
        doc = _build_channel_document(channel)
        await client.index(
            index=f"{index_prefix}_content",
            id=str(channel.channel_id),
            body=doc,
        )
    except Exception as exc:
        logger.warning("OpenSearch channel indexing failed for %s: %s", channel.channel_id, exc)


# ---------------------------------------------------------------------------
# Celery task stubs (wired up once Celery worker is provisioned)
# ---------------------------------------------------------------------------


def celery_sync_post_task(post_id: str, index_prefix: str) -> None:
    """Celery task stub for async post indexing.

    TODO: Replace with @app.task decorator once Celery worker is configured.
    Currently unused — BackgroundTask hook is the primary indexing path.
    """
    raise NotImplementedError(
        "Celery worker not yet configured. "
        "Use sync_post_to_opensearch() as a FastAPI BackgroundTask instead."
    )


def celery_sync_channel_task(channel_id: str, index_prefix: str) -> None:
    """Celery task stub for async channel indexing."""
    raise NotImplementedError(
        "Celery worker not yet configured. "
        "Use sync_channel_to_opensearch() as a FastAPI BackgroundTask instead."
    )
