# Content Service — Search & Feed Architecture

Technical documentation covering the search infrastructure, feed recommendation algorithms, caching strategy, and A/B experimentation framework.

---

## Table of Contents

1. [Search Infrastructure](#1-search-infrastructure)
2. [Feed & Recommendation Algorithm](#2-feed--recommendation-algorithm)
3. [Cold-Start Handling](#3-cold-start-handling)
4. [Caching Strategy](#4-caching-strategy)
5. [A/B Testing & Experiments](#5-ab-testing--experiments)
6. [Database Indexes & Performance](#6-database-indexes--performance)

---

## 1. Search Infrastructure

### Dual-Path Architecture

The service implements **OpenSearch as the primary search engine** with an automatic **PostgreSQL GIN-index fallback** when OpenSearch is unavailable or disabled (`opensearch_enabled=False`).

### 1.1 OpenSearch Index Schema

Two indexes are maintained with an environment-configurable prefix (e.g. `dev_content`, `prod_content`):

#### Content Index (`{prefix}_content`)

| Field | Type | Boost | Description |
|-------|------|-------|-------------|
| `content_id` | keyword | — | Post / channel / course UUID |
| `content_type` | keyword | — | `POST`, `REPOST`, `CHANNEL`, `COURSE`, `WEBINAR` |
| `title` | text | **3.0** | Primary search field (highest weight) |
| `body_snippet` | text | 1.0 | First 500 characters of body / description |
| `specialty_tags` | keyword | **2.0** | Controlled taxonomy tags |
| `hashtags` | keyword | **1.5** | Freeform user hashtags |
| `author_id` | keyword | — | Post author / channel owner |
| `pricing_type` | keyword | — | `FREE` / `PAID` (courses, webinars) |
| `duration_mins` | integer | — | Course / webinar duration |
| `created_at` | date | — | Publication timestamp |
| `popularity_score` | float | — | Pre-computed engagement metric |

**Index settings:** 1 shard, 1 replica.

**Popularity score formula:**

```
popularity_score = like_count + (comment_count × 2) + (share_count × 3)
```

#### User Index (`{prefix}_user`)

Used for people search. Fields: `user_id`, `full_name`, `specialty`, `role`, `verification_status`, `location` (geo_point). Populated by the identity service.

### 1.2 Indexing Pipeline

Documents are indexed via **FastAPI BackgroundTasks** triggered after post publish, edit, or soft-delete.

| Event | Action |
|-------|--------|
| Post publish / edit | `sync_post_to_opensearch` — upserts document with current metadata and engagement score |
| Channel create / edit | `sync_channel_to_opensearch` — indexed as `content_type=CHANNEL` |
| Post soft-delete | `delete_post_from_opensearch` — removes document (idempotent, `ignore=404`) |

Indexing is **non-blocking**: failures are logged but never raised to the request path.

**Document structure:**

```json
{
  "content_id": "post_uuid",
  "content_type": "POST",
  "title": "Post title",
  "body_snippet": "First 500 chars...",
  "specialty_tags": ["healthcare", "oncology"],
  "hashtags": ["#cancer", "#awareness"],
  "author_id": "user_uuid",
  "pricing_type": null,
  "duration_mins": null,
  "created_at": "2024-02-27T10:30:00Z",
  "popularity_score": 42.0
}
```

### 1.3 Search Query Construction

#### Full Search (BM25 Multi-Match)

```json
{
  "query": {
    "bool": {
      "must": [{
        "multi_match": {
          "query": "<user_query>",
          "fields": ["title^3", "specialty_tags^2", "hashtags^1.5", "body_snippet"],
          "type": "best_fields",
          "fuzziness": "AUTO"
        }
      }],
      "filter": [
        { "term": { "content_type": "POST" } },
        { "terms": { "specialty_tags": ["tag1", "tag2"] } },
        { "term": { "pricing_type": "FREE" } }
      ]
    }
  },
  "aggs": {
    "content_type_facets": { "terms": { "field": "content_type", "size": 10 } },
    "specialty_tag_facets": { "terms": { "field": "specialty_tags", "size": 20 } },
    "hashtag_facets": { "terms": { "field": "hashtags", "size": 30 } }
  }
}
```

**Key design decisions:**

- **`best_fields`** strategy: the single best-matching field determines the score, avoiding dilution across fields.
- **`fuzziness: AUTO`**: tolerates typos proportional to term length.
- **Facet aggregations** returned alongside results for filter UI (content type counts, top 20 specialty tags, top 30 hashtags).
- All filters in the `filter` clause are optional and applied only when the client provides them.

#### Autocomplete / Suggest

Uses `phrase_prefix` matching on `title^3`, `specialty_tags^2`, `hashtags^1.5`. Returns lightweight payloads (`content_id`, `content_type`, `title`, tags).

### 1.4 PostgreSQL Fallback

When OpenSearch is disabled, search falls back to PostgreSQL full-text search:

```sql
ts_vector = to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))
ts_query  = plainto_tsquery('english', <query>)

WHERE ts_vector @@ ts_query
  AND status IN ('PUBLISHED', 'EDITED')
  AND visibility = 'PUBLIC'
ORDER BY ts_rank(ts_vector, ts_query) DESC, created_at DESC
```

Supported by three GIN indexes:

| Index | Target |
|-------|--------|
| `ix_posts_fts` | Full-text search on `title + body` |
| `ix_posts_specialty_tags` | Array containment for tag filtering |
| `ix_posts_hashtags` | Array containment for hashtag filtering |

---

## 2. Feed & Recommendation Algorithm

### 2.1 Feed Types Overview

| Feed | Ranking Logic | Pagination |
|------|--------------|------------|
| **For You** | Composite scored (personalized) | Offset-based |
| **Following** | Reverse chronological from followed users | Cursor-based, 500-post hard cap |
| **Trending** | Highest engagement in last 48h | Offset-based |
| **Public** | Reverse chronological | Offset-based |
| **Channel** | Reverse chronological within channel | Offset-based |
| **User Profile** | Reverse chronological by author | Offset-based |

### 2.2 "For You" Feed — Three-Signal Composite Score

The personalized feed uses a weighted composite of three signals:

```
Score = (W_recency × Recency) + (W_specialty × Specialty) + (W_affinity × Affinity)
```

**Default weights:**

| Signal | Weight | Description |
|--------|--------|-------------|
| Recency | **0.40** | How fresh the post is |
| Specialty | **0.30** | Topic relevance to user interests |
| Affinity | **0.30** | Historical interaction with the author |

Weights are configurable per cohort and per A/B experiment variant (see Section 5).

#### Signal 1: Recency (Exponential Decay)

```
recency_score = 2^(-hours_old / 24)
```

Half-life of **24 hours**:

| Post Age | Score |
|----------|-------|
| 0 hours | 1.000 |
| 12 hours | 0.707 |
| 24 hours | 0.500 |
| 48 hours | 0.250 |
| 7 days | ~0.008 |

Candidate posts are fetched from a **7-day rolling window** (max 500 candidates).

#### Signal 2: Specialty / Topic Relevance

Binary tag-overlap scoring against the user's declared interests:

```python
specialty_score = 1.0  if overlap(post.specialty_tags, user.interests)
                  0.7  if only overlap(post.hashtags, user.interests)
                  0.0  otherwise
```

Controlled taxonomy tags are treated as higher-confidence signals than freeform hashtags (0.7 discount).

#### Signal 3: Affinity (Author Interaction History)

Measures how much the current user has historically engaged with a post's author.

**Interaction point weights:**

| Action | Points |
|--------|--------|
| Like | 1.0 |
| Comment | 3.0 |
| Share | 5.0 |

**Calculation:**

```
raw_affinity = (likes_with_author × 1) + (comments_with_author × 3) + (shares_with_author × 5)
affinity_score = min(1.0, raw_affinity / affinity_ceiling)
```

Default `affinity_ceiling` = **50.0** points. Example: 10 likes + 2 comments + 1 share = 10 + 6 + 5 = 21 → 21/50 = **0.42**.

Affinity scores are **batch-resolved** per unique author in the candidate set and cached in Redis (see Section 4).

### 2.3 For You Feed Pipeline

```
Request arrives
    │
    ▼
1. Resolve effective weights (default → cohort → experiment variant)
    │
    ▼
2. Cold-start check: user has < 10 total interactions?
    │── Yes → Cold-start feed (Section 3)
    │── No  ▼
    │
3. Fetch up to 500 candidate posts from last 7 days
   (PUBLIC, PUBLISHED/EDITED, exclude user's own posts)
    │
    ▼
4. Extract unique author IDs from candidates
    │
    ▼
5. Batch-resolve affinity scores (Redis L1 → PostgreSQL L2)
    │
    ▼
6. Score each candidate:
   score = (W_r × recency) + (W_s × specialty) + (W_a × affinity)
    │
    ▼
7. Sort by score DESC → apply offset/limit pagination
    │
    ▼
8. Return scored results
```

### 2.4 Following Feed

- Strictly **reverse chronological** from accounts the user follows.
- **Cursor-based pagination** using `(created_at, post_id)` as a composite cursor for stable ordering.
- **Hard cap of 500 posts** per feed session. Cumulative depth is tracked across paginated requests; returns `is_exhausted=True` when the cap is reached.

### 2.5 Trending Feed

Ranks posts by engagement score over a **48-hour window**:

```
engagement = like_count + (comment_count × 2) + (share_count × 3)
```

Results are **Redis-cached for 5 minutes** (key: `feed:trending`).

---

## 3. Cold-Start Handling

Activated when the user has **fewer than 10 total interactions** (likes + comments + shares).

### Blended Composition

| Segment | Share | Source |
|---------|-------|--------|
| Editor Picks | **20%** | Manually curated posts (priority-ordered by admins) |
| Trending | **40%** | Highest engagement in last 48h |
| Specialty-matched | **40%** | Posts matching user's onboarding interests from last 7 days |

Posts are **deduplicated** across segments — each post appears at most once.

### Editor Picks

- Managed via admin endpoints: `add_editor_pick(post_id, priority, added_by)`.
- `priority` is ascending (0 = highest).
- Soft-delete via `is_active` flag.

### Transition to Warm Start

Automatic — once a user accumulates 10+ interactions, subsequent For You feed requests use the full composite scoring pipeline.

---

## 4. Caching Strategy

### Redis Cache Keys

| Key Pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `feed:{user_id}:affinity:{author_id}` | float | **1 hour** | Per-author affinity score |
| `feed:trending` | JSON list | **5 min** | Ordered trending post IDs |
| `experiments:weights:{user_id}:{cohort_hash}` | JSON | **60 sec** | Resolved weight configuration |
| `content:fingerprint:{hash}:{author_id}` | "1" | **60 sec** | Duplicate content spam guard (SETNX) |

### Affinity Caching Flow

```
Request for affinity scores (batch of author_ids)
    │
    ▼
L1: Redis pipeline GET for all author_ids
    │
    ├── Cache hits → return immediately
    │
    ├── Cache misses ▼
    │
    L2: PostgreSQL GROUP BY queries
        - Likes by author
        - Comments by author
        - Shares by author
    │
    ▼
    Compute raw_affinity → normalize → write back to Redis (1h TTL)
```

Batch pipeline reduces Redis round-trips to **one GET call + one SET call** regardless of author count.

---

## 5. A/B Testing & Experiments

### 5.1 Cohort System

Cohorts group users by characteristics and assign custom feed algorithm parameters:

```json
{
  "name": "High-engagement users",
  "feed_algorithm": {
    "recency": 0.35,
    "specialty": 0.35,
    "affinity": 0.30,
    "cold_start_threshold": 5,
    "affinity_ceiling": 100.0
  },
  "priority": 10,
  "is_active": true
}
```

- Cohort membership is resolved **externally** (API gateway or client) and passed via `cohort_ids` query parameter.
- When multiple cohorts apply, the **highest-priority** cohort's weights are used.

### 5.2 A/B Experiment Structure

Experiments are attached to cohorts and define multi-variant tests:

```json
{
  "cohort_id": "uuid",
  "name": "Increase affinity weight",
  "status": "RUNNING",
  "variants": [
    {
      "name": "control",
      "traffic_pct": 50,
      "algorithm_config": { "recency": 0.40, "specialty": 0.30, "affinity": 0.30 }
    },
    {
      "name": "treatment",
      "traffic_pct": 50,
      "algorithm_config": { "recency": 0.30, "specialty": 0.30, "affinity": 0.40 }
    }
  ]
}
```

**Constraints:** minimum 2 variants, `traffic_pct` must sum to 100, minimum 7-day duration.

### 5.3 Deterministic Variant Assignment

Uses **SHA-256 hashing** — no server-side state required:

```python
bucket = int(SHA256(f"{user_id}:{experiment_id}").hexdigest(), 16) % 100

# Walk cumulative traffic_pct to find variant
cumulative = 0
for variant in variants:
    cumulative += variant.traffic_pct
    if bucket < cumulative:
        return variant
```

Properties: deterministic (same user always gets same variant), stateless, uniformly distributed.

### 5.4 Weight Resolution Priority

```
1. Check for RUNNING experiment on highest-priority active cohort
   └── Found → use experiment variant's algorithm_config
2. Else use cohort's feed_algorithm
3. Else use global defaults (0.40 / 0.30 / 0.30)
```

Resolved config is cached in Redis for 60 seconds.

### 5.5 Experiment Metrics

**Events ingested:** `IMPRESSION`, `CLICK`, `LIKE`, `SESSION_START`, `SESSION_END` (with duration).

**Metrics computed per variant:**

| Metric | Formula |
|--------|---------|
| CTR | clicks / impressions |
| CTR confidence interval | Wilson score (95% CI) |
| Likes per session | likes / session_starts |
| Avg session duration | mean(session_duration_s) |

**Statistical significance:** Treatment is significant when its CTR CI lower bound exceeds the control's CTR CI upper bound.

### 5.6 Experiment Lifecycle

```
DRAFT → RUNNING → PAUSED → COMPLETED
          ↕
       (resumable)
```

Updates allowed only in `DRAFT` or `PAUSED` state.

---

## 6. Database Indexes & Performance

### Post Table Indexes

| Index | Type | Columns |
|-------|------|---------|
| `ix_posts_author_id` | B-tree | `author_id` |
| `ix_posts_status` | B-tree | `status` |
| `ix_posts_created_at` | B-tree | `created_at` |
| `ix_posts_specialty_tags` | GIN | `specialty_tags` (array) |
| `ix_posts_hashtags` | GIN | `hashtags` (array) |
| `ix_posts_fts` | GIN | `tsvector(title \|\| body)` |

### Interaction Table Indexes

Optimized for `(user_id, target_id)` lookups and `GROUP BY author_id` aggregations used in affinity computation.

### Performance Targets

- **Design capacity:** 3,000–5,000 feed reads/second
- **Search latency:** Sub-100ms via OpenSearch; ~200ms via PostgreSQL GIN fallback
- **Affinity resolution:** Single Redis pipeline call for batch lookups
- **Candidate window:** 7-day limit caps query scan range
- **Following feed:** 500-post hard cap prevents unbounded queries
- **Trending:** 5-minute cache eliminates repeated heavy aggregations
