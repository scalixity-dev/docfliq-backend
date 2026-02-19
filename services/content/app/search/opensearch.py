"""OpenSearch client wrapper and index mappings.

Two indexes are managed by this service:
  {prefix}_content  — posts (and eventually courses/webinars)
  {prefix}_user     — user profiles (populated by identity service; stub here)

Index creation is idempotent (checkfirst=True pattern via ignore=400).
The client is obtained via the `get_opensearch` FastAPI dependency (set in lifespan).
When OpenSearch is disabled (`opensearch_enabled=False`), all operations
are no-ops and the client is None.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Index mappings
# ---------------------------------------------------------------------------

CONTENT_INDEX_MAPPING: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
    },
    "mappings": {
        "properties": {
            "content_id":       {"type": "keyword"},
            # POST / COURSE / WEBINAR — used for faceting and type-scoped queries
            "content_type":     {"type": "keyword"},
            "title":            {"type": "text", "boost": 3},
            # First 500 chars of body/description — used for search preview snippets
            "body_snippet":     {"type": "text"},
            "specialty_tags":   {"type": "keyword", "boost": 2},
            "author_id":        {"type": "keyword"},
            # FREE / PAID — facet filter for courses and webinars
            "pricing_type":     {"type": "keyword"},
            # Duration in minutes — range filter for courses/webinars; null for posts
            "duration_mins":    {"type": "integer"},
            "created_at":       {"type": "date"},
            # Pre-computed score: like_count + comment_count×2 + share_count×3
            "popularity_score": {"type": "float"},
        }
    },
}

USER_INDEX_MAPPING: dict[str, Any] = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
    },
    "mappings": {
        "properties": {
            "user_id":              {"type": "keyword"},
            "full_name":            {"type": "text"},
            "specialty":            {"type": "keyword"},
            "role":                 {"type": "keyword"},
            "verification_status":  {"type": "keyword"},
            "location":             {"type": "geo_point"},
        }
    },
}


# ---------------------------------------------------------------------------
# Index management helpers
# ---------------------------------------------------------------------------


async def ensure_indexes(client, index_prefix: str) -> None:
    """Create content and user indexes if they don't exist.

    Uses `ignore=400` to silently skip if the index already exists.
    Call once at startup when opensearch_enabled=True.
    """
    content_index = f"{index_prefix}_content"
    user_index = f"{index_prefix}_user"

    await client.indices.create(
        index=content_index,
        body=CONTENT_INDEX_MAPPING,
        ignore=400,
    )
    await client.indices.create(
        index=user_index,
        body=USER_INDEX_MAPPING,
        ignore=400,
    )


# ---------------------------------------------------------------------------
# Content search
# ---------------------------------------------------------------------------


async def search_content(
    client,
    index_prefix: str,
    query: str,
    content_type: str | None = None,
    specialty_tags: list[str] | None = None,
    pricing_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Execute a BM25 multi-match search against the content index.

    Fields: title^3, specialty_tags^2, body_snippet
    Includes facet aggregations on content_type and specialty_tags terms.
    Filters are applied as `filter` clauses (don't affect relevance scoring).
    """
    must: list[dict] = []
    filter_clauses: list[dict] = []

    if query:
        must.append({
            "multi_match": {
                "query": query,
                "fields": ["title^3", "specialty_tags^2", "body_snippet"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        })
    else:
        must.append({"match_all": {}})

    if content_type:
        filter_clauses.append({"term": {"content_type": content_type}})
    if specialty_tags:
        filter_clauses.append({"terms": {"specialty_tags": specialty_tags}})
    if pricing_type:
        filter_clauses.append({"term": {"pricing_type": pricing_type}})

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filter_clauses,
            }
        },
        "aggs": {
            "content_type_facets": {
                "terms": {"field": "content_type", "size": 10}
            },
            "specialty_tag_facets": {
                "terms": {"field": "specialty_tags", "size": 20}
            },
        },
        "from": offset,
        "size": limit,
    }

    return await client.search(
        index=f"{index_prefix}_content",
        body=body,
    )


async def suggest_content(
    client,
    index_prefix: str,
    partial: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Prefix suggestion query across title and specialty_tags."""
    body = {
        "query": {
            "multi_match": {
                "query": partial,
                "fields": ["title^3", "specialty_tags^2"],
                "type": "phrase_prefix",
            }
        },
        "size": limit,
        "_source": ["content_id", "content_type", "title", "specialty_tags"],
    }
    return await client.search(index=f"{index_prefix}_content", body=body)


# ---------------------------------------------------------------------------
# User search (stub — populated by identity service)
# ---------------------------------------------------------------------------


async def search_users(
    client,
    index_prefix: str,
    query: str,
    specialty: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search user index. Returns empty hits when index is unpopulated."""
    must: list[dict] = []
    filter_clauses: list[dict] = []

    if query:
        must.append({
            "multi_match": {
                "query": query,
                "fields": ["full_name^2"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        })
    else:
        must.append({"match_all": {}})

    if specialty:
        filter_clauses.append({"term": {"specialty": specialty}})

    body = {
        "query": {"bool": {"must": must, "filter": filter_clauses}},
        "from": offset,
        "size": limit,
    }
    return await client.search(index=f"{index_prefix}_user", body=body, ignore=404)
