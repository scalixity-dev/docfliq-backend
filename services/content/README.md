# Content Microservice

Social content engine for the Docfliq platform. Handles post lifecycle, personalised feeds,
full-text search, social interactions, and feed A/B experimentation.

---

## Table of Contents

1. [Stack & Infrastructure](#stack--infrastructure)
2. [Project Structure](#project-structure)
3. [Architecture Pattern](#architecture-pattern)
4. [Domain Guide](#domain-guide)
   - [CMS](#1-cms--post--channel-management)
   - [Feed](#2-feed--personalised-content-delivery)
   - [Search](#3-search--full-text--faceted-search)
   - [Interactions](#4-interactions--social-layer)
   - [Experiments](#5-experiments--ab-testing--cohorts)
5. [Algorithms in Detail](#algorithms-in-detail)
   - [For-You Feed Scoring](#for-you-feed-scoring)
   - [Cold-Start Handling](#cold-start-handling)
   - [Trending Score](#trending-score)
   - [Affinity Accumulation](#affinity-accumulation)
   - [Search: Dual-Path Strategy](#search-dual-path-strategy)
   - [A/B Variant Assignment](#ab-variant-assignment)
   - [Results & Statistical Significance](#results--statistical-significance)
6. [Data Models](#data-models)
7. [Enums Reference](#enums-reference)
8. [API Endpoints Summary](#api-endpoints-summary)
9. [Configuration](#configuration)
10. [Running Locally](#running-locally)
11. [Database Migrations](#database-migrations)
12. [Status: Complete / Partial / Blocked](#status-complete--partial--blocked)
13. [External Service Dependencies](#external-service-dependencies)
14. [Known Gaps & Future Work](#known-gaps--future-work)

---

## Stack & Infrastructure

| Layer           | Technology                                      |
|-----------------|-------------------------------------------------|
| Framework       | FastAPI (async)                                 |
| ORM             | SQLAlchemy 2.0 async (`asyncpg`)                |
| Database        | PostgreSQL (primary store)                      |
| Cache           | Redis (affinity, trending, rate-limit, weights) |
| Search          | OpenSearch (primary) + PostgreSQL GIN (fallback)|
| Auth            | JWT HS256 — decoded in `dependencies.py`        |
| Validation      | Pydantic V2                                     |
| Migrations      | Alembic (async)                                 |
| Shared lib      | `shared/` (`Base`, middleware, session factory) |

The service is fully async end-to-end (DB, Redis, OpenSearch).

---

## Project Structure

```
services/content/
├── app/
│   ├── main.py               # App factory, router registration, CORS, middleware
│   ├── config.py             # Pydantic Settings (env vars)
│   ├── dependencies.py       # JWT auth, Redis client, OpenSearch client
│   ├── database.py           # Async session factory
│   ├── exceptions.py         # Shared HTTP exception classes
│   ├── pagination.py         # CursorPage, OffsetPage, cursor encode/decode
│   │
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── enums.py          # All PgEnum definitions
│   │   ├── post.py
│   │   ├── post_version.py
│   │   ├── comment.py
│   │   ├── interaction.py    # Like, Bookmark, Share
│   │   ├── social.py         # Report
│   │   ├── channel.py
│   │   ├── editor_pick.py
│   │   └── cohort.py         # Cohort, ABExperiment, ExperimentEvent
│   │
│   ├── cms/                  # Post & channel lifecycle
│   ├── feed/                 # Feed strategies + scoring
│   ├── search/               # Full-text + faceted search
│   ├── interactions/         # Like, comment, bookmark, repost, share, report
│   └── experiments/          # Cohorts, A/B tests, weight resolution, telemetry
│
├── tests/
├── Dockerfile
└── requirements.txt
```

Each domain follows the same internal layout:

```
<domain>/
├── router.py      # HTTP only: methods, status codes, response_model, Depends
├── controller.py  # Catch domain exceptions → HTTPException, compose responses
├── service.py     # Pure business logic, no FastAPI/HTTP imports
├── schemas.py     # Pydantic V2: separate Create/Update (input) vs Response (output)
└── exceptions.py  # Domain-specific exception classes
```

---

## Architecture Pattern

```
Client
  └─► router.py        (HTTP: params, auth, response_model)
        └─► controller.py  (orchestration, error mapping)
              └─► service.py    (pure business logic)
                    └─► ORM models / Redis / OpenSearch
```

**Key rules:**
- Services never import FastAPI or raise `HTTPException`.
- Controllers never touch the database directly.
- Routers never call services directly.
- All DB access uses SQLAlchemy 2.0 style: `select(Model).where(...)` + `db.execute(...)`.
- Primary-key lookups use `db.get(Model, pk)` (avoids a round-trip `SELECT`).
- After `INSERT`/`UPDATE`: `await db.flush()` + `await db.refresh(obj)` before the response
  (session is `expire_on_commit=False`).

---

## Domain Guide

### 1. CMS — Post & Channel Management

**What it does:** Full post lifecycle from draft to published, versioned edit history,
soft deletion with 30-day retention, and channel management.

**Business rules:**
- `DRAFT → PUBLISHED` via explicit `/publish` call.
- Editing a `PUBLISHED` or `EDITED` post:
  - Snapshots current state to `post_versions`.
  - Increments `post.version`.
  - Sets `status = EDITED`.
- Soft delete: sets `status = SOFT_DELETED`, `deleted_at = now()`.
  The post is hidden from all public feeds but still readable by the author.
- Admin hide: `status = HIDDEN_BY_ADMIN` — hidden from author too.
- Duplicate guard: same author + same content fingerprint within 60 seconds → `409 Conflict`.
- Channel slugs are auto-generated from the channel name and must be globally unique.
- Version history and restoration are author-only.

**Notable endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/cms/posts` | Create a post (TEXT / IMAGE / VIDEO / LINK) |
| `PATCH` | `/cms/posts/{post_id}` | Edit (snapshots version, sets EDITED) |
| `DELETE` | `/cms/posts/{post_id}` | Soft delete |
| `POST` | `/cms/posts/{post_id}/publish` | DRAFT → PUBLISHED |
| `POST` | `/cms/posts/{post_id}/hide` | Admin: HIDDEN_BY_ADMIN |
| `GET` | `/cms/posts/{post_id}/versions` | Edit history (author-only) |
| `POST` | `/cms/posts/{post_id}/restore` | Restore a historical version |
| `GET` | `/cms/my-posts` | All my posts regardless of status |
| `POST` | `/cms/channels` | Create channel (auto-slug) |
| `PATCH` | `/cms/channels/{channel_id}` | Update channel (owner-only) |

---

### 2. Feed — Personalised Content Delivery

**What it does:** Six feed strategies serving different surfaces.
The core innovation is the **For-You feed**: a composite scored, cohort-aware,
experiment-driven ranked feed with cold-start handling.

#### Feed Strategies

| Strategy | Pagination | Auth | Description |
|----------|-----------|------|-------------|
| Public | Offset | Optional | All live posts, reverse-chronological |
| For You | Offset | Required | Scored: recency + specialty + affinity, cohort-aware |
| Following | Cursor | Required | Posts from followed users, hard 500-post cap |
| Trending | Cached | None | Top engagement score, last 48h, 5-min Redis cache |
| Channel | Offset | Optional | Posts belonging to a specific channel |
| User Profile | Offset | Optional | Public posts by a specific user |
| Editor Picks | None | Admin | Admin-curated list, priority-ordered |

#### Supporting files

- `feed/scoring.py` — Pure scoring functions (zero I/O, fully unit-testable).
- `feed/cache.py` — Redis helpers for affinity, trending, and duplicate fingerprints.

---

### 3. Search — Full-Text & Faceted Search

**What it does:** Unified search across posts, channels, people, courses, and webinars.
Uses OpenSearch as the primary engine with a PostgreSQL GIN index as a graceful fallback.

#### Dual-Path Strategy

```
Request
  ├─► opensearch_enabled = True  → OpenSearch  (BM25, facets, fuzzy, field boosts)
  └─► opensearch_enabled = False → Postgres GIN (to_tsvector FTS + array containment)
```

**OpenSearch index fields and boosts:**

| Field | Boost | Notes |
|-------|-------|-------|
| `title` | 3× | Primary signal |
| `specialty_tags` | 2× | Array keyword field |
| `body_snippet` | 1× | Plain text |
| `pricing_type` | — | Keyword filter |
| `duration_mins` | — | Integer range filter |
| `popularity_score` | — | Float, used for boost |

Searches use BM25 multi-match with `fuzziness=AUTO`.

**Indexing pipeline:**
- On publish / edit: `BackgroundTask → sync_post_to_opensearch()`
- On soft-delete: `BackgroundTask → delete_post_from_opensearch()`
- Failures are logged and never raise (non-blocking to the API response).

**Endpoints:**

| Method | Path | Status |
|--------|------|--------|
| `GET` | `/search` | Unified search (top N per section) — complete |
| `GET` | `/search/posts` | Post FTS + facets — complete |
| `GET` | `/search/channels` | Channel name/description ILIKE — complete |
| `GET` | `/search/suggest` | Autocomplete (phrase_prefix) — complete |
| `GET` | `/search/people` | People search — **stub, needs identity service** |
| `GET` | `/search/courses` | Course search — **stub, needs course content indexed** |
| `GET` | `/search/webinars` | Webinar search — **stub, needs webinar content indexed** |

---

### 4. Interactions — Social Layer

**What it does:** Full social interaction graph — likes, comment threads, bookmarks,
reposts, external share tracking, and content reports with auto-moderation.

**Business rules:**
- Like / bookmark: idempotent creation; returns `409` if already exists.
- Comments: max depth 2 (no replies to replies), max 2,000 characters per comment.
- Comment rate limit: 5 per minute per user (Redis counter, 60-second window).
- Repost chains collapse to root: if the original is itself a `REPOST`,
  `original_post_id` is set to `original.original_post_id` (no chain-of-chains).
- Reposts and external shares both increment `share_count` on the root post.
- Like / comment counters are denormalised on `Post` for O(1) feed reads.
- Reports: once a post or comment accumulates 5+ `OPEN` reports,
  the target is automatically set to `HIDDEN_BY_ADMIN` / `HIDDEN`.
- Self-reports are rejected (`reporter_id == target_id` for `USER` target type).

**Endpoints (15 total):**

| Method | Path | Description |
|--------|------|-------------|
| `POST/DELETE` | `/interactions/posts/{id}/like` | Like / unlike a post |
| `POST/DELETE` | `/interactions/comments/{id}/like` | Like / unlike a comment |
| `GET/POST` | `/interactions/posts/{id}/comments` | List / add comments |
| `PATCH/DELETE` | `/interactions/comments/{id}` | Edit / delete comment |
| `POST/DELETE` | `/interactions/posts/{id}/bookmark` | Bookmark / remove |
| `GET` | `/interactions/bookmarks` | List my bookmarks |
| `POST` | `/interactions/posts/{id}/repost` | Repost (creates REPOST post) |
| `POST` | `/interactions/posts/{id}/share` | Track external share |
| `POST` | `/interactions/posts/{id}/report` | Report a post |
| `POST` | `/interactions/comments/{id}/report` | Report a comment |

---

### 5. Experiments — A/B Testing & Cohorts

**What it does:** Admin-managed cohort system that segments users and allows
multiple feed algorithm variants to be tested simultaneously.
The system is **stateless** — variant assignment is deterministic and never stored.

**Concepts:**

- **Cohort** — A named user segment with a custom `feed_algorithm` config
  (recency weight, specialty weight, affinity weight, cold-start threshold, affinity ceiling)
  and a `priority` (lower number = higher precedence when a user belongs to multiple cohorts).
  User membership is resolved externally (by the API gateway or client) and passed as
  `cohort_ids` query parameters. The content service never decides who is in a cohort.

- **ABExperiment** — A multi-variant test scoped to a cohort.
  Each variant carries its own `algorithm_config` overriding the cohort defaults.
  Variants must sum to 100% traffic. Lifecycle: `DRAFT → RUNNING → PAUSED → COMPLETED`.
  Minimum 7-day duration is enforced when `end_date` is set.

- **ExperimentEvent** — Per-user telemetry row.
  Types: `IMPRESSION`, `CLICK`, `LIKE`, `COMMENT`, `SHARE`, `SESSION_START`, `SESSION_END`.

**Endpoints (12 total):**

| Method | Path | Description |
|--------|------|-------------|
| `POST/GET` | `/experiments/cohorts` | Create / list cohorts |
| `GET/PATCH/DELETE` | `/experiments/cohorts/{id}` | CRUD on a cohort |
| `POST/GET` | `/experiments` | Create / list experiments |
| `GET/PATCH` | `/experiments/{id}` | Get / update experiment |
| `POST` | `/experiments/{id}/start` | DRAFT/PAUSED → RUNNING |
| `POST` | `/experiments/{id}/pause` | RUNNING → PAUSED |
| `POST` | `/experiments/{id}/complete` | → COMPLETED |
| `GET` | `/experiments/{id}/results` | Compute CTR + session metrics (Wilson CI) |
| `GET` | `/experiments/weights` | Resolve effective weights for the For-You feed |
| `POST` | `/experiments/events` | Ingest telemetry event |

---

## Algorithms in Detail

### For-You Feed Scoring

Every candidate post receives a composite score in `[0, 1]`:

```
score = w_r × recency + w_s × specialty + w_a × affinity
```

**Default weights** (overridable per cohort / experiment variant):

| Weight | Default | Meaning |
|--------|---------|---------|
| `w_r` (recency) | 0.40 | How recently the post was published |
| `w_s` (specialty) | 0.30 | Tag overlap between post and user interests |
| `w_a` (affinity) | 0.30 | How much the user has interacted with this author |

**Recency score** — exponential decay with a 24-hour half-life:

```
recency = 2^(−hours_since_published / 24)
```

A post published 24 hours ago scores 0.50; 48 hours ago scores 0.25.

**Specialty score** — binary tag match for now:

```
specialty = 1.0  if any(tag in user_interests)
specialty = 0.0  otherwise
```

> A "related specialty" (partial overlap, 0.5) is intentionally deferred
> pending the specialty taxonomy design.

**Affinity score** — normalised accumulated interaction points:

```
raw_points = likes × 1 + comments × 3 + shares × 5
affinity   = min(1.0, raw_points / affinity_ceiling)   # ceiling default = 50
```

Affinity values are read from Redis (TTL 1h, per `(user_id, author_id)` pair)
to avoid recomputing on every request.

**Candidate window:** last 7 days, up to 500 posts fetched, scored in Python, then sorted.
Pagination is applied after scoring so page N always returns the N-th best posts.

---

### Cold-Start Handling

A user with fewer than `cold_start_threshold` (default 10) interactions is in cold-start.
Instead of scoring, the feed is assembled from three buckets:

```
20%  Editor Picks   (admin-curated, priority-ordered)
40%  Trending       (highest engagement score, last 48h)
40%  Specialty      (posts matching user's declared interests, recency-sorted)
```

Once the user crosses the threshold, they graduate to the full scoring algorithm.

---

### Trending Score

```
engagement = like_count + comment_count × 2 + share_count × 3
```

Computed over the last 48 hours. Result is cached in Redis for 5 minutes
(`feed:trending` key) to avoid a heavy aggregation query on every request.

---

### Affinity Accumulation

Affinity is not stored in the database. On each For-You feed request:

1. Three `GROUP BY` queries aggregate likes, comments, and shares
   from the current user to each author across all time.
2. Raw points are converted to a normalised score.
3. Results are written back to Redis (`feed:{user_id}:affinity:{author_id}`, TTL 1h).
4. On the next request within the TTL window, Redis is read directly (no DB query).

> **Gap:** Profile-visit signals are not included in affinity because that event
> lives in the identity service. See [Known Gaps](#known-gaps--future-work).

---

### Search: Dual-Path Strategy

```
opensearch_enabled = True
  └─► AsyncOpenSearch query
        ├─► Multi-match BM25 on (title^3, specialty_tags^2, body_snippet)
        ├─► fuzziness = AUTO (typo tolerance)
        ├─► Filters: content_type, specialty_tags, pricing_type, date range
        └─► Facets: aggregations on content_type, specialty_tags

opensearch_enabled = False  (or OpenSearch unavailable)
  └─► PostgreSQL GIN
        ├─► to_tsvector('english', title || ' ' || body) plainto_tsquery match
        └─► specialty_tags @> ARRAY[...] containment (GIN array index)
```

**Indexing:** BackgroundTasks are fired after every publish/edit/delete.
If OpenSearch is not configured (`opensearch_enabled=False`), indexing is skipped silently.

---

### A/B Variant Assignment

Variant assignment is **deterministic and stateless** — the same user always
lands in the same variant for the same experiment, with no database write.

```python
raw   = SHA-256(f"{user_id}{experiment_id}").hexdigest()
bucket = int(raw, 16) % 100   # bucket in [0, 99]
```

Variants are sorted by name. The bucket is mapped to a variant by cumulative
traffic percentages (e.g., variant A = 0–49, variant B = 50–99 for a 50/50 split).

**Weight resolution flow** for the For-You feed:

```
cohort_ids empty?
  └─► return DEFAULT_WEIGHT_CONFIG

Check Redis cache (key: experiments:weights:{user_id}:{sha(cohort_ids)}, TTL 60s)
  └─► cache hit → return cached config

Fetch highest-priority active cohort from DB

RUNNING experiment on this cohort?
  ├─► Yes → assign variant (SHA-256) → return variant.algorithm_config  (source: "experiment:name:variant")
  └─► No  → return cohort.feed_algorithm                                (source: "cohort")

Write to Redis cache, return
```

---

### Results & Statistical Significance

`GET /experiments/{id}/results` aggregates `experiment_events` and computes:

| Metric | Formula |
|--------|---------|
| CTR | `clicks / impressions` |
| CTR 95% CI | Wilson score interval |
| Likes per session | `likes / session_starts` |
| Avg session length | `mean(session_duration_s)` |

**Statistical significance:** a treatment variant is considered significant
when its Wilson CI lower bound exceeds the control variant's CI upper bound.

Results are written back to `experiment.results` (JSONB) for caching.

---

## Data Models

### Post

| Column | Type | Notes |
|--------|------|-------|
| `post_id` | UUID PK | |
| `author_id` | UUID | Soft-ref to identity_db |
| `content_type` | enum | TEXT / IMAGE / VIDEO / LINK / WEBINAR_CARD / COURSE_CARD / REPOST |
| `title` | VARCHAR(300) | nullable |
| `body` | TEXT | nullable |
| `media_urls` | JSONB | `[{url, type, thumbnail}]` |
| `link_preview` | JSONB | `{url, og_title, og_image, og_description}` |
| `visibility` | enum | PUBLIC / VERIFIED_ONLY / FOLLOWERS_ONLY |
| `status` | enum | DRAFT / PUBLISHED / EDITED / SOFT_DELETED / HIDDEN_BY_ADMIN |
| `specialty_tags` | TEXT[] | GIN-indexed |
| `like_count` | INT | Denormalised counter |
| `comment_count` | INT | Denormalised counter |
| `share_count` | INT | Denormalised counter |
| `bookmark_count` | INT | Denormalised counter |
| `version` | INT | Incremented on each edit |
| `channel_id` | UUID FK | nullable |
| `original_post_id` | UUID FK (self) | REPOST chains only |
| `deleted_at` | TIMESTAMP | Set on soft-delete (30-day retention) |

**Indexes:** `author_id`, `status`, `created_at`, GIN on `specialty_tags`, GIN FTS on `title || body`.

### PostVersion (edit snapshot)

Stores the full content of a post at each edit point.
`version_number` matches `post.version` at time of edit.

### Comment

Self-referential: `parent_comment_id` references another comment (max depth 2 enforced at app layer).
Statuses: `ACTIVE / HIDDEN / DELETED`.

### Like

Polymorphic: `target_type` (POST or COMMENT) + `target_id` (UUID).
Unique constraint on `(user_id, target_type, target_id)`.

### Report

Polymorphic: `target_type` (USER / POST / COMMENT / WEBINAR) + `target_id`.
Status flow: `OPEN → REVIEWED → ACTIONED / DISMISSED`.

### Cohort / ABExperiment / ExperimentEvent

See [Experiments domain](#5-experiments--ab-testing--cohorts) above.

---

## Enums Reference

```
ContentType         TEXT | IMAGE | VIDEO | LINK | WEBINAR_CARD | COURSE_CARD | REPOST
PostVisibility      PUBLIC | VERIFIED_ONLY | FOLLOWERS_ONLY
PostStatus          DRAFT | PUBLISHED | EDITED | SOFT_DELETED | HIDDEN_BY_ADMIN
CommentStatus       ACTIVE | HIDDEN | DELETED
LikeTargetType      POST | COMMENT
ReportTargetType    USER | POST | COMMENT | WEBINAR
ReportStatus        OPEN | REVIEWED | ACTIONED | DISMISSED
ExperimentStatus    DRAFT | RUNNING | PAUSED | COMPLETED
ExperimentEventType IMPRESSION | CLICK | LIKE | COMMENT | SHARE | SESSION_START | SESSION_END
```

All enums are `PgEnum` with `create_type=True` (DDL managed by Alembic).

---

## API Endpoints Summary

All routes are prefixed with `/api/v1`. Interactive docs available at `/docs` and `/redoc`.

| Tag | Prefix | Count | Purpose |
|-----|--------|-------|---------|
| CMS | `/cms` | 13 | Post & channel lifecycle |
| Feed | `/feed` | 10 | Feed variants + editor picks |
| Search | `/search` | 6 | Post/channel/people/course/webinar search |
| Interactions | `/interactions` | 15 | Like, comment, bookmark, repost, share, report |
| Experiments | `/experiments` | 12 | Cohorts, A/B tests, weights, telemetry |
| Health | `/health` | 1 | Liveness probe |

**Total: 57 endpoints.**

---

## Configuration

All settings are loaded from environment variables via `app/config.py` (Pydantic `BaseSettings`).

| Variable | Required | Description |
|----------|----------|-------------|
| `CONTENT_DATABASE_URL` | Yes | PostgreSQL async DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | Redis DSN (`redis://...`) |
| `JWT_SECRET` | Yes | Shared HS256 secret (must match identity service) |
| `ENV_NAME` | No | `development` / `staging` / `production` |
| `CORS_ORIGINS` | No | JSON array or comma-separated list of allowed origins |
| `OPENSEARCH_URL` | No | OpenSearch node URL (e.g., `http://localhost:9200`) |
| `OPENSEARCH_ENABLED` | No | `true` / `false` (default `false`) |
| `OPENSEARCH_INDEX_PREFIX` | No | Prefix for index names (default `docfliq`) |

---

## Running Locally

```bash
# 1. Install dependencies (from repo root)
pip install -r services/content/requirements.txt

# 2. Set environment variables
export CONTENT_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/content_db
export REDIS_URL=redis://localhost:6379
export JWT_SECRET=dev-secret

# 3. Apply migrations
cd migrations/content
alembic upgrade head

# 4. Start the service
cd services/content
uvicorn app.main:app --reload --port 8001
```

OpenSearch is optional. If `OPENSEARCH_ENABLED=false` (default), all search falls back
to PostgreSQL GIN with no facets.

---

## Database Migrations

Migration files live in `migrations/content/alembic/versions/`.

| Revision | Description |
|----------|-------------|
| `001_initial_content` | Initial schema |
| `2937ecd0` | Drop follow/block tables — moved to identity service |
| `31ff7a88` | Post, channel, comment, interaction tables |
| `a1b2c3d4` | REPOST content type, EDITED/SOFT_DELETED/HIDDEN_BY_ADMIN statuses, `original_post_id`, `deleted_at`, `post_versions` table |
| `c3d4e5f6` | `editor_picks` table |
| `d5e6f7a8` | `cohorts`, `ab_experiments`, `experiment_events` tables + new enums |

To create a new migration:

```bash
cd migrations/content
alembic revision --autogenerate -m "describe_the_change"
alembic upgrade head
```

---

## Status: Complete / Partial / Blocked

### Complete

- Post CRUD with full lifecycle (DRAFT, PUBLISHED, EDITED, SOFT_DELETED, HIDDEN_BY_ADMIN)
- Edit history snapshots and version restoration
- Channel management (create, update, deactivate, slug generation)
- All six feed strategies (public, for-you, following, trending, channel, user profile)
- For-You scoring algorithm (recency + specialty + affinity + cold-start)
- Trending cache and engagement scoring
- Affinity computation and Redis caching
- Comment threading (2 levels) with rate limiting
- Likes, bookmarks, reposts, external share tracking
- Auto-moderation (5+ reports → auto-hide)
- Report lifecycle (OPEN → REVIEWED → ACTIONED / DISMISSED)
- Cohort management (CRUD, priority, feed algorithm config)
- A/B experiment lifecycle (DRAFT → RUNNING → PAUSED → COMPLETED)
- Deterministic stateless variant assignment (SHA-256)
- Weight resolution with Redis caching
- Experiment results with Wilson CI for CTR
- OpenSearch index mappings and BM25 post search
- PostgreSQL GIN fallback for post search
- Channel search (ILIKE)
- Autocomplete (phrase_prefix)
- Unified search (top N per section)
- BackgroundTask-based OpenSearch indexing (non-blocking)
- Cursor and offset pagination utilities
- JWT auth middleware (HS256, `payload["sub"]`)
- Request ID and error envelope middlewares
- Health endpoint

### Partially Done — Works but has known limitations

| Feature | What works | What is missing |
|---------|-----------|-----------------|
| Specialty scoring | Binary (match=1.0, no match=0.0) | "Related specialty" partial score (0.5) awaits taxonomy design |
| Affinity scoring | Like/comment/share signals | Profile-visit signal lives in identity service, not integrated |
| Search — people | Endpoint exists, returns results from user_index | user_index is never populated (identity service must index users) |
| Search — courses | Endpoint exists, filters content_index by COURSE_CARD | Requires course service to push records to OpenSearch |
| Search — webinars | Endpoint exists, filters content_index by WEBINAR_CARD | Requires webinar service to push records to OpenSearch |
| OpenSearch indexing | BackgroundTask path works | Celery-based async task stubs exist but raise `NotImplementedError` |
| Admin RBAC | Endpoints exist | Gating delegated to API gateway; no built-in role check |
| Soft-delete retention | `deleted_at` is set | 30-day cleanup job not implemented |

### Blocked — Needs another service before it can work

See [External Service Dependencies](#external-service-dependencies) below.

---

## External Service Dependencies

This service intentionally uses **soft foreign keys** (UUIDs only, no DB-level FK to other services).
The following integrations are expected but not yet wired:

### 1. Identity Service (critical)

**What is needed:**

- **JWT tokens** — The content service validates HS256 tokens and reads `payload["sub"]`
  as the user UUID. The identity service must issue tokens with that exact structure
  and the same `JWT_SECRET`.

- **User data on feed responses** — Feed and search responses currently return
  `author_id` (UUID) only. To show `author_name`, `author_avatar`, `is_verified`,
  and `is_followed` on posts, the feed controller must call the identity service
  (or a shared read model) to hydrate those fields. This is **not yet implemented**.

- **Follow graph** — The following tab (`GET /feed/following`) accepts a `followed_ids`
  query parameter (list of UUIDs). The caller (client or API gateway) must supply these.
  The content service does not store follow relationships. The identity service owns them.

- **User interests** — The For-You feed accepts an `interests` query parameter.
  The caller must supply the user's declared specialties. There is no internal
  interest-store in the content service.

- **Cohort membership** — `cohort_ids` query param on `/feed/for-you` and
  `/experiments/weights` must be resolved by the caller. The content service
  does not evaluate cohort rules against user attributes.

- **Profile-visit affinity signal** — Profile visits are tracked in identity service.
  This signal is not incorporated into the affinity score today.

### 2. Notification Service (not started)

The following events should trigger push/in-app notifications but currently do not:

| Event | Expected notification |
|-------|-----------------------|
| Someone likes your post | "X liked your post" |
| Someone comments on your post | "X commented on your post" |
| Someone reposts your post | "X reposted your post" |
| Your report was actioned | "Your report has been reviewed" |
| Post auto-hidden (5 reports) | Notify author |

**What needs to be built:** After each interaction is persisted, fire an event
(HTTP call, message queue, or webhook) to the notification service with
`{event_type, actor_id, target_user_id, post_id}`.

### 3. Course & Webinar Services (stubs only)

`GET /search/courses` and `GET /search/webinars` query OpenSearch `content_index`
filtered by `content_type = COURSE_CARD` and `WEBINAR_CARD` respectively.
These return empty results today because:

- No course/webinar service is indexing into OpenSearch yet.
- The `WEBINAR_CARD` and `COURSE_CARD` post types exist in the schema
  (a Docfliq author can post a webinar/course card), but the richer search
  (filtering by price, duration, specialty) is designed for content owned by
  dedicated services.

**What needs to be done:** Course and webinar services should push their
records to `{prefix}_content` OpenSearch index using the same schema
(fields: `content_id`, `content_type`, `title`, `body_snippet`,
`specialty_tags`, `pricing_type`, `duration_mins`, `popularity_score`).

### 4. API Gateway / Auth Proxy (assumed present)

The content service assumes the API gateway handles:

- **Admin role gating** for: `POST /cms/posts/{id}/hide`, `POST/DELETE /feed/editor-picks`,
  and all `/experiments/cohorts` and `/experiments` write endpoints.
  There is no built-in RBAC inside the content service.

- **Rate limiting** at the gateway level (beyond the per-user comment rate limit
  which is enforced internally via Redis).

- **Token refresh** — expired tokens return `401`; the gateway should handle
  refresh-token flows before forwarding to this service.

---

## Known Gaps & Future Work

| # | Gap | Priority | Notes |
|---|-----|----------|-------|
| 1 | Author hydration on feed/search responses | High | Needs identity service call or a shared read model |
| 2 | Notification events on interactions | High | Fire-and-forget call/queue after like, comment, repost |
| 3 | Soft-delete cleanup job | Medium | Purge posts where `deleted_at < now() - 30 days` |
| 4 | Celery async indexing | Medium | Replace BackgroundTask with Celery tasks for reliability; stubs in `search/indexer.py` |
| 5 | Related-specialty scoring (0.5) | Medium | Partial tag-overlap scoring awaits taxonomy design |
| 6 | Profile-visit affinity signal | Medium | Consume visit events from identity service |
| 7 | Built-in admin RBAC | Low | Currently delegated to API gateway |
| 8 | `FOLLOWERS_ONLY` visibility enforcement | Low | Post visibility flag exists but feed queries don't filter by follow graph yet |
| 9 | `VERIFIED_ONLY` visibility enforcement | Low | Same as above — requires identity service verification flag |
| 10 | OpenSearch index rehydration script | Low | Bulk re-index all existing posts into OpenSearch on first deployment |
| 11 | Pagination on comment replies | Low | Top-level comments are paginated; replies are returned in full |
| 12 | Experiment auto-completion | Low | No background job to auto-complete experiments past `end_date` |

---

*Last updated: 2026-02-19*
