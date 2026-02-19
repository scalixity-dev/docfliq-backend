"""Search service — pure business logic, no FastAPI imports.

Dual-path strategy:
  - When OpenSearch client is available (opensearch_enabled=True):
      Posts/channels → OpenSearch (BM25, facets, typo-tolerance)
      People/courses/webinars → OpenSearch (stub indexes, return empty until other services populate)
  - When OpenSearch is None (opensearch_enabled=False):
      Posts/channels → PostgreSQL GIN fallback
      People/courses/webinars → empty stub response

Full-text (Postgres) uses the GIN index on posts:
  ix_posts_fts = GIN( to_tsvector('english', coalesce(title,'') || ' ' || coalesce(body,'')) )
Tag filtering uses:
  ix_posts_specialty_tags = GIN(specialty_tags)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.enums import ContentType, PostStatus, PostVisibility
from app.models.post import Post
from app.search import opensearch as os_helpers
from app.search.schemas import (
    ChannelSearchResult,
    CourseSearchResult,
    FacetBucket,
    PeopleSearchResult,
    PostSearchResult,
    SearchFacets,
    SuggestItem,
    WebinarSearchResult,
)

_LIVE_STATUSES = (PostStatus.PUBLISHED, PostStatus.EDITED)


# ---------------------------------------------------------------------------
# Post search
# ---------------------------------------------------------------------------


async def search_posts(
    db: AsyncSession,
    os_client,
    index_prefix: str,
    query: str | None = None,
    tags: list[str] | None = None,
    content_type: ContentType | None = None,
    channel_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Post], int, SearchFacets | None]:
    """Dual-path post search. Returns (posts, total, facets_or_None)."""
    if os_client is not None:
        return await _search_posts_opensearch(
            os_client, index_prefix, query, tags, content_type, limit, offset
        )
    posts, total = await _search_posts_postgres(db, query, tags, content_type, channel_id, limit, offset)
    return posts, total, None


async def _search_posts_opensearch(
    client,
    index_prefix: str,
    query: str | None,
    tags: list[str] | None,
    content_type: ContentType | None,
    limit: int,
    offset: int,
) -> tuple[list[Any], int, SearchFacets]:
    """OpenSearch path — returns raw hit dicts, total, and facets."""
    raw = await os_helpers.search_content(
        client=client,
        index_prefix=index_prefix,
        query=query or "",
        content_type=content_type.value if content_type else None,
        specialty_tags=tags,
        limit=limit,
        offset=offset,
    )
    hits = raw.get("hits", {})
    total = hits.get("total", {}).get("value", 0)
    docs = [h["_source"] for h in hits.get("hits", [])]

    # Parse facets from aggregations
    aggs = raw.get("aggregations", {})
    ct_buckets = [
        FacetBucket(value=b["key"], count=b["doc_count"])
        for b in aggs.get("content_type_facets", {}).get("buckets", [])
    ]
    tag_buckets = [
        FacetBucket(value=b["key"], count=b["doc_count"])
        for b in aggs.get("specialty_tag_facets", {}).get("buckets", [])
    ]
    facets = SearchFacets(content_type=ct_buckets, specialty_tags=tag_buckets)
    return docs, total, facets


async def _search_posts_postgres(
    db: AsyncSession,
    query: str | None,
    tags: list[str] | None,
    content_type: ContentType | None,
    channel_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Post], int]:
    """PostgreSQL GIN fallback for post search."""
    base = select(Post).where(
        Post.status.in_(_LIVE_STATUSES),
        Post.visibility == PostVisibility.PUBLIC,
    )

    if content_type is not None:
        base = base.where(Post.content_type == content_type)
    if channel_id is not None:
        base = base.where(Post.channel_id == channel_id)
    if tags:
        base = base.where(Post.specialty_tags.contains(tags))

    order_by_clauses = [Post.created_at.desc()]

    if query:
        ts_query = func.plainto_tsquery("english", query)
        ts_vector = func.to_tsvector(
            "english",
            func.coalesce(Post.title, "") + " " + func.coalesce(Post.body, ""),
        )
        base = base.where(ts_vector.op("@@")(ts_query))
        order_by_clauses = [func.ts_rank(ts_vector, ts_query).desc(), Post.created_at.desc()]

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(base.order_by(*order_by_clauses).offset(offset).limit(limit))
    return list(result.scalars().all()), total


# ---------------------------------------------------------------------------
# Channel search
# ---------------------------------------------------------------------------


async def search_channels(
    db: AsyncSession,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Channel], int]:
    """Search active channels by name or description (ILIKE) — Postgres only."""
    base = select(Channel).where(Channel.is_active.is_(True))

    if query:
        pattern = f"%{query}%"
        base = base.where(
            Channel.name.ilike(pattern) | Channel.description.ilike(pattern)
        )

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(base.order_by(Channel.name.asc()).offset(offset).limit(limit))
    return list(result.scalars().all()), total


# ---------------------------------------------------------------------------
# People search (stub)
# ---------------------------------------------------------------------------


async def search_people(
    os_client,
    index_prefix: str,
    query: str | None = None,
    specialty: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[PeopleSearchResult], int]:
    """Search user_index (stub — returns empty list when index is unpopulated)."""
    if os_client is None:
        return [], 0
    try:
        raw = await os_helpers.search_users(
            client=os_client,
            index_prefix=index_prefix,
            query=query or "",
            specialty=specialty,
            limit=limit,
            offset=offset,
        )
        hits = raw.get("hits", {}) if raw else {}
        total = hits.get("total", {}).get("value", 0)
        results = [
            PeopleSearchResult(
                user_id=h["_source"].get("user_id"),
                full_name=h["_source"].get("full_name", ""),
                specialty=h["_source"].get("specialty"),
                role=h["_source"].get("role"),
                verification_status=h["_source"].get("verification_status"),
            )
            for h in hits.get("hits", [])
        ]
        return results, total
    except Exception:
        return [], 0


# ---------------------------------------------------------------------------
# Course / Webinar search (stubs — content_type filter on content_index)
# ---------------------------------------------------------------------------


async def _search_typed_content(
    os_client,
    index_prefix: str,
    content_type_value: str,
    query: str | None,
    specialty_tags: list[str] | None,
    pricing_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Common OpenSearch search for COURSE or WEBINAR content_type."""
    if os_client is None:
        return [], 0
    try:
        raw = await os_helpers.search_content(
            client=os_client,
            index_prefix=index_prefix,
            query=query or "",
            content_type=content_type_value,
            specialty_tags=specialty_tags,
            pricing_type=pricing_type,
            limit=limit,
            offset=offset,
        )
        hits = raw.get("hits", {}) if raw else {}
        total = hits.get("total", {}).get("value", 0)
        docs = [h["_source"] for h in hits.get("hits", [])]
        return docs, total
    except Exception:
        return [], 0


async def search_courses(
    os_client,
    index_prefix: str,
    query: str | None = None,
    specialty_tags: list[str] | None = None,
    pricing_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CourseSearchResult], int]:
    docs, total = await _search_typed_content(
        os_client, index_prefix, "COURSE", query, specialty_tags, pricing_type, limit, offset
    )
    return [
        CourseSearchResult(
            content_id=d.get("content_id", ""),
            title=d.get("title", ""),
            body_snippet=d.get("body_snippet", ""),
            specialty_tags=d.get("specialty_tags", []),
            pricing_type=d.get("pricing_type"),
            duration_mins=d.get("duration_mins"),
            popularity_score=float(d.get("popularity_score", 0)),
            created_at=d.get("created_at"),
        )
        for d in docs
    ], total


async def search_webinars(
    os_client,
    index_prefix: str,
    query: str | None = None,
    specialty_tags: list[str] | None = None,
    pricing_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[WebinarSearchResult], int]:
    docs, total = await _search_typed_content(
        os_client, index_prefix, "WEBINAR", query, specialty_tags, pricing_type, limit, offset
    )
    return [
        WebinarSearchResult(
            content_id=d.get("content_id", ""),
            title=d.get("title", ""),
            body_snippet=d.get("body_snippet", ""),
            specialty_tags=d.get("specialty_tags", []),
            pricing_type=d.get("pricing_type"),
            duration_mins=d.get("duration_mins"),
            popularity_score=float(d.get("popularity_score", 0)),
            created_at=d.get("created_at"),
        )
        for d in docs
    ], total


# ---------------------------------------------------------------------------
# Autocomplete suggest
# ---------------------------------------------------------------------------


async def suggest(
    os_client,
    index_prefix: str,
    partial: str,
    limit: int = 10,
) -> list[SuggestItem]:
    """Autocomplete using phrase_prefix multi-match against title and specialty_tags."""
    if os_client is None or not partial:
        return []
    try:
        raw = await os_helpers.suggest_content(
            client=os_client,
            index_prefix=index_prefix,
            partial=partial,
            limit=limit,
        )
        hits = raw.get("hits", {}).get("hits", [])
        return [
            SuggestItem(
                content_id=h["_source"].get("content_id", ""),
                content_type=h["_source"].get("content_type", ""),
                title=h["_source"].get("title", ""),
                specialty_tags=h["_source"].get("specialty_tags", []),
            )
            for h in hits
        ]
    except Exception:
        return []
