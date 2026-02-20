# Course & LMS Microservice (MS-3)

Owns complete learning management: courses, catalog, enrollment, video playback
with resume, assessments, progress tracking, SCORM wrapper, and certificate
generation with QR verification.

---

## Table of Contents

1. [Stack & Infrastructure](#stack--infrastructure)
2. [Project Structure](#project-structure)
3. [Architecture Pattern](#architecture-pattern)
4. [Domain Guide](#domain-guide)
   - [LMS](#1-lms--course--module--lesson--enrollment--progress)
   - [Assessment](#2-assessment--quizzes--grading)
   - [Certificates](#3-certificates--generation--verification)
5. [Course Structure](#course-structure)
6. [Enrollment Flows](#enrollment-flows)
   - [Free Enrollment](#free-enrollment)
   - [Paid Enrollment](#paid-enrollment)
   - [Edge Cases](#enrollment-edge-cases)
7. [Status Transitions](#status-transitions)
8. [Data Models](#data-models)
9. [Enums Reference](#enums-reference)
10. [API Endpoints Summary](#api-endpoints-summary)
11. [Swagger / OpenAPI Docs](#swagger--openapi-docs)
12. [Configuration](#configuration)
13. [Running Locally](#running-locally)
14. [Database Migrations](#database-migrations)
15. [External Service Dependencies](#external-service-dependencies)
16. [Known Gaps & Future Work](#known-gaps--future-work)

---

## Stack & Infrastructure

| Layer           | Technology                                      |
|-----------------|-------------------------------------------------|
| Framework       | FastAPI (async)                                 |
| ORM             | SQLAlchemy 2.0 async (`asyncpg`)                |
| Database        | PostgreSQL (primary store)                      |
| Cache           | Redis (session state, rate limits)              |
| Auth            | JWT HS256 — decoded in `dependencies.py`        |
| Validation      | Pydantic V2                                     |
| Migrations      | Alembic (async)                                 |
| Shared lib      | `shared/` (`Base`, middleware, session factory)  |

The service is fully async end-to-end (DB, Redis).

---

## Project Structure

```
services/course/
├── app/
│   ├── main.py               # App factory, router registration, CORS, middleware
│   ├── config.py             # Pydantic Settings (env vars)
│   ├── dependencies.py       # JWT auth, Redis client
│   ├── database.py           # Async session factory
│   ├── exceptions.py         # Shared domain exception classes
│   ├── pagination.py         # OffsetPage, CursorPage, cursor encode/decode
│   │
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── enums.py          # All PgEnum definitions
│   │   ├── course.py         # Course (top-level container)
│   │   ├── course_module.py  # CourseModule (logical grouping)
│   │   ├── lesson.py         # Lesson (VIDEO, PDF, TEXT, QUIZ, SCORM)
│   │   ├── quiz.py           # Quiz (MCQ questions in JSONB)
│   │   ├── enrollment.py     # Enrollment (user_id + course_id)
│   │   ├── lesson_progress.py # LessonProgress (per-lesson tracking)
│   │   └── certificate.py    # Certificate (QR verification code)
│   │
│   ├── lms/                  # Course lifecycle + enrollment + progress
│   │   ├── router.py         # 22 endpoints
│   │   ├── controller.py     # Error mapping, response composition
│   │   ├── service.py        # Pure business logic
│   │   └── schemas.py        # Pydantic V2 request/response models
│   │
│   ├── assessment/           # Quiz CRUD + attempt scoring
│   │   ├── router.py         # 7 endpoints
│   │   ├── controller.py
│   │   ├── service.py
│   │   └── schemas.py
│   │
│   └── certificates/         # Certificate generation + QR verification
│       ├── router.py         # 4 endpoints
│       ├── controller.py
│       ├── service.py
│       └── schemas.py
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
└── schemas.py     # Pydantic V2: separate Create/Update (input) vs Response (output)
```

---

## Architecture Pattern

```
Client
  └─► router.py        (HTTP: params, auth, response_model)
        └─► controller.py  (orchestration, error mapping)
              └─► service.py    (pure business logic)
                    └─► ORM models / Redis
```

**Key rules:**
- Services never import FastAPI or raise `HTTPException`.
- Controllers never touch the database directly.
- Routers never call services directly.
- All DB access uses SQLAlchemy 2.0 style: `select(Model).where(...)` + `db.execute(...)`.
- Primary-key lookups use `db.get(Model, pk)`.
- After `INSERT`/`UPDATE`: `await db.flush()` + `await db.refresh(obj)`.

---

## Domain Guide

### 1. LMS — Course, Module, Lesson, Enrollment, Progress

**What it does:** Full course lifecycle from draft to published, hierarchical
content structure (Course > Module > Lesson), enrollment management for both
free and paid courses, video resume/playback tracking, and automatic progress
calculation.

**Course management (instructor):**
- Create a course (defaults to DRAFT status)
- Auto-generate SEO slug from title (with uniqueness check)
- Update course metadata (title, description, pricing, etc.)
- Publish: `DRAFT → PUBLISHED`
- Archive: `PUBLISHED/DRAFT → ARCHIVED` (soft delete — enrolled users retain access)

**Module management:**
- Add modules to a course (ordered by `sort_order`)
- Reorder modules via a single PATCH with ordered `module_ids` array
- Update/delete modules (cascades to lessons)
- `total_modules` counter on Course is auto-maintained

**Lesson management:**
- Add lessons to a module (types: VIDEO, PDF, TEXT, QUIZ, SCORM)
- `is_preview` flag allows unenrolled users to preview specific lessons
- `total_duration_mins` on Course is auto-maintained from lesson durations
- Delete cascades quiz if attached

**Enrollment:**
- Free enrollment: instant access on PUBLISHED + FREE courses
- Paid enrollment: requires `payment_id` from MS-6 (Payment Service)
- Unique constraint `(user_id, course_id)` prevents double enrollment
- Drop: sets status to `DROPPED` (re-enrollment possible)
- Progress initialized at 0%, auto-calculated as lessons are completed

**Progress tracking:**
- Per-lesson progress: track `watch_duration_secs`, mark `completed`
- Resume position: `last_lesson_id` + `last_position_secs` on enrollment
- When lesson is completed, `progress_pct` is recalculated as:
  `completed_lessons / total_lessons × 100`
- When all lessons are completed, enrollment status → `COMPLETED`

---

### 2. Assessment — Quizzes & Grading

**What it does:** MCQ quiz creation by instructors, student attempt submission
with automatic scoring, attempt tracking with configurable retry limits.

**Business rules:**
- One quiz per lesson (unique constraint)
- Questions stored as JSONB array: `{question, options[], correct_index, explanation}`
- Student view strips `correct_index` and `explanation` from questions
- Scoring: `correct_count / total_questions × 100` (rounded to integer percentage)
- Pass threshold: configurable `passing_score` per quiz (default 70%)
- Max attempts: optional cap per quiz. When reached, returns `400`
- On quiz pass: lesson progress status → `COMPLETED`
- Attempt number is tracked per `(enrollment, lesson)` pair

---

### 3. Certificates — Generation & Verification

**What it does:** Certificate issuance upon course completion with a unique
QR verification code. Public verification endpoint for QR scan.

**Business rules:**
- Certificate generation requires enrollment status = `COMPLETED`
- One certificate per enrollment (unique constraint)
- QR verification code: SHA-256 hash (24-char hex), globally unique
- Certificate URL: placeholder for S3 PDF generation (future integration)
- Public verification endpoint (no auth) returns: validity, course title, issue date

---

## Course Structure

| Level       | Description | Example |
|-------------|-------------|---------|
| **Course**  | Top-level container: title, description, instructor, price, specialty, thumbnail, preview video | Advanced Cardiac Imaging Techniques |
| **Module**  | Logical grouping of lessons. Ordered sequentially. | Module 1: Fundamentals of Echocardiography |
| **Lesson**  | Individual unit: video, PDF document, text, or SCORM package | Lesson 1.1: Transthoracic Echo (Video, 25 min) |
| **Assessment** | Quiz after lessons or end of module/course. MCQ format. | Module 1 Quiz: 10 questions, passing 70% |

---

## Enrollment Flows

### Free Enrollment

1. User calls `POST /api/v1/lms/courses/{id}/enroll`
2. Backend validates: course is PUBLISHED + pricing_type is FREE
3. Creates enrollment (status=IN_PROGRESS, progress_pct=0%)
4. Instant access. Enrollment count incremented.

### Paid Enrollment

| Step | Actor | Action | Failure Handling |
|------|-------|--------|-----------------|
| 1 | User | Clicks Buy Now. Frontend calls MS-6 for Razorpay checkout. | Razorpay API failure: retry 3× with backoff. Show "Payment unavailable". |
| 2 | User | Completes payment on Razorpay. | Abandons: order stays INITIATED. Cleanup after 24h. |
| 3 | Razorpay | Webhook to MS-6. Validates signature. Emits `payment.success`. | Signature mismatch: reject. Log security alert. |
| 4 | MS-3 | Consumes event or client calls `POST /api/v1/lms/courses/{id}/enroll/paid` with `payment_id`. Creates enrollment. | Event lost: reconciliation job every 15 min catches it. |

### Enrollment Edge Cases

| Scenario | Handling |
|----------|----------|
| Payment success but enrollment event lost | Reconciliation job every 15 min: queries MS-6 for successful payments, cross-references enrollments, creates missing ones. |
| Double payment (double-click) | Unique constraint `(user_id, course_id)`. Second enrollment attempt returns `409 Conflict`. |
| Course deleted while enrolled | Soft delete (ARCHIVED) only. Enrolled users retain access. Removed from catalog. |
| Refund after partial completion | Eligible if <20% complete and within 7 days. Access revoked on refund. |

---

## Status Transitions

### Course Status

```
DRAFT ──► PUBLISHED ──► ARCHIVED
  │                        ▲
  └────────────────────────┘
```

- `DRAFT → PUBLISHED`: via `POST /courses/{id}/publish`
- `PUBLISHED → ARCHIVED`: via `POST /courses/{id}/archive`
- `DRAFT → ARCHIVED`: via `POST /courses/{id}/archive`
- Archived courses are hidden from catalog but enrolled users retain access.

### Enrollment Status

```
IN_PROGRESS ──► COMPLETED  (all lessons done)
     │
     └──► DROPPED  (user drops)
```

### Lesson Progress Status

```
NOT_STARTED ──► IN_PROGRESS ──► COMPLETED
```

---

## Data Models

### Course

| Column | Type | Notes |
|--------|------|-------|
| `course_id` | UUID PK | |
| `title` | VARCHAR(300) | |
| `slug` | VARCHAR(300) | Unique, SEO-friendly |
| `description` | TEXT | nullable |
| `instructor_id` | UUID | Soft-ref to identity_db |
| `institution_id` | UUID | nullable, soft-ref |
| `category` | VARCHAR(100) | e.g. Featured, By Specialty |
| `specialty_tags` | TEXT[] | GIN-indexed |
| `pricing_type` | ENUM | FREE / PAID |
| `price` | NUMERIC(10,2) | nullable, > 0 for PAID |
| `currency` | VARCHAR(3) | default INR |
| `preview_video_url` | VARCHAR(500) | CloudFront URL |
| `thumbnail_url` | VARCHAR(500) | |
| `syllabus` | JSONB | `[{module_title, topics: [str]}]` |
| `completion_logic` | JSONB | `{score_threshold, pct_required}` |
| `total_modules` | SMALLINT | Denormalized counter |
| `total_duration_mins` | INT | Denormalized |
| `enrollment_count` | INT | Denormalized |
| `rating_avg` | NUMERIC(3,2) | nullable |
| `status` | ENUM | DRAFT / PUBLISHED / ARCHIVED |
| `visibility` | ENUM | PUBLIC / VERIFIED_ONLY |
| `scorm_package_url` | VARCHAR(500) | S3 URL |
| `created_at` / `updated_at` | TIMESTAMP(tz) | |

**Indexes:** `instructor_id`, `status`, `category`, `created_at`, GIN on `specialty_tags`, GIN FTS on `title || description`.

### CourseModule

| Column | Type | Notes |
|--------|------|-------|
| `module_id` | UUID PK | |
| `course_id` | UUID FK → courses | CASCADE delete |
| `title` | VARCHAR(300) | |
| `sort_order` | SMALLINT | |
| `created_at` | TIMESTAMP(tz) | |

### Lesson

| Column | Type | Notes |
|--------|------|-------|
| `lesson_id` | UUID PK | |
| `module_id` | UUID FK → course_modules | CASCADE delete |
| `title` | VARCHAR(300) | |
| `lesson_type` | ENUM | VIDEO / PDF / TEXT / QUIZ / SCORM |
| `content_url` | VARCHAR(500) | S3 signed URL |
| `content_body` | TEXT | Rich text for TEXT type |
| `duration_mins` | INT | nullable |
| `sort_order` | SMALLINT | |
| `is_preview` | BOOLEAN | default false |
| `created_at` | TIMESTAMP(tz) | |

### Quiz

| Column | Type | Notes |
|--------|------|-------|
| `quiz_id` | UUID PK | |
| `lesson_id` | UUID FK → lessons | CASCADE delete |
| `questions` | JSONB | `[{question, options[], correct_index, explanation}]` |
| `passing_score` | SMALLINT | default 70 |
| `max_attempts` | SMALLINT | nullable = unlimited |
| `created_at` | TIMESTAMP(tz) | |

### Enrollment

| Column | Type | Notes |
|--------|------|-------|
| `enrollment_id` | UUID PK | |
| `user_id` | UUID | Soft-ref to identity_db |
| `course_id` | UUID FK → courses | CASCADE delete |
| `payment_id` | UUID | nullable, soft-ref to payment_db |
| `progress_pct` | NUMERIC(5,2) | 0.00–100.00 |
| `status` | ENUM | IN_PROGRESS / COMPLETED / DROPPED |
| `completed_at` | TIMESTAMP(tz) | nullable |
| `last_lesson_id` | UUID FK → lessons | Resume pointer |
| `last_position_secs` | INT | Video resume position |
| `created_at` | TIMESTAMP(tz) | |

**Constraints:** Unique `(user_id, course_id)`.

### LessonProgress

| Column | Type | Notes |
|--------|------|-------|
| `progress_id` | UUID PK | |
| `enrollment_id` | UUID FK → enrollments | CASCADE delete |
| `lesson_id` | UUID FK → lessons | CASCADE delete |
| `status` | ENUM | NOT_STARTED / IN_PROGRESS / COMPLETED |
| `watch_duration_secs` | INT | nullable |
| `quiz_score` | SMALLINT | nullable, 0–100 |
| `quiz_attempts` | SMALLINT | nullable |
| `completed_at` | TIMESTAMP(tz) | nullable |

**Constraints:** Unique `(enrollment_id, lesson_id)`.

### Certificate

| Column | Type | Notes |
|--------|------|-------|
| `certificate_id` | UUID PK | |
| `enrollment_id` | UUID FK → enrollments | Unique, CASCADE delete |
| `user_id` | UUID | Soft-ref |
| `course_id` | UUID FK → courses | CASCADE delete |
| `certificate_url` | VARCHAR(500) | S3 PDF URL |
| `qr_verification_code` | VARCHAR(100) | Unique, 24-char hex |
| `issued_at` | TIMESTAMP(tz) | |

---

## Enums Reference

```
PricingType          FREE | PAID
CourseStatus         DRAFT | PUBLISHED | ARCHIVED
CourseVisibility     PUBLIC | VERIFIED_ONLY
LessonType           VIDEO | PDF | TEXT | QUIZ | SCORM
EnrollmentStatus     IN_PROGRESS | COMPLETED | DROPPED
LessonProgressStatus NOT_STARTED | IN_PROGRESS | COMPLETED
```

All enums are `PgEnum` with `create_type=True` (DDL managed by Alembic).

---

## API Endpoints Summary

All routes are prefixed with `/api/v1`. Interactive docs available at `/docs` and `/redoc`.

### LMS — Course, Module, Lesson, Enrollment, Progress (22 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/lms/courses` | Required | Create a new course (DRAFT) |
| `GET` | `/lms/courses` | None | List/search courses (catalog) |
| `GET` | `/lms/courses/{course_id}` | None | Get course by ID |
| `GET` | `/lms/courses/slug/{slug}` | None | Get course by slug (SEO) |
| `GET` | `/lms/courses/{course_id}/detail` | None | Get course with modules + lessons |
| `PATCH` | `/lms/courses/{course_id}` | Required | Update course (instructor only) |
| `POST` | `/lms/courses/{course_id}/publish` | Required | DRAFT → PUBLISHED |
| `POST` | `/lms/courses/{course_id}/archive` | Required | Soft delete (archive) |
| `POST` | `/lms/courses/{course_id}/modules` | Required | Add module |
| `PATCH` | `/lms/modules/{module_id}` | Required | Update module |
| `DELETE` | `/lms/modules/{module_id}` | Required | Delete module |
| `PATCH` | `/lms/courses/{course_id}/modules/reorder` | Required | Reorder modules |
| `POST` | `/lms/modules/{module_id}/lessons` | Required | Add lesson |
| `PATCH` | `/lms/lessons/{lesson_id}` | Required | Update lesson |
| `DELETE` | `/lms/lessons/{lesson_id}` | Required | Delete lesson |
| `POST` | `/lms/courses/{course_id}/enroll` | Required | Free enrollment |
| `POST` | `/lms/courses/{course_id}/enroll/paid` | Required | Paid enrollment |
| `GET` | `/lms/enrollments/me` | Required | List my enrollments |
| `GET` | `/lms/enrollments/{enrollment_id}` | Required | Enrollment detail + progress |
| `DELETE` | `/lms/enrollments/{enrollment_id}` | Required | Drop course |
| `POST` | `/lms/lessons/{lesson_id}/progress` | Required | Update lesson progress |
| `POST` | `/lms/enrollments/{enrollment_id}/resume` | Required | Update resume position |
| `GET` | `/lms/courses/{course_id}/progress` | Required | Get full course progress |

### Assessment — Quizzes & Grading (7 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/assessment/lessons/{lesson_id}/quiz` | Required | Create quiz (instructor) |
| `GET` | `/assessment/lessons/{lesson_id}/quiz` | None | Get quiz (student view, no answers) |
| `GET` | `/assessment/quizzes/{quiz_id}` | Required | Get quiz (instructor view, with answers) |
| `PATCH` | `/assessment/quizzes/{quiz_id}` | Required | Update quiz |
| `DELETE` | `/assessment/quizzes/{quiz_id}` | Required | Delete quiz |
| `POST` | `/assessment/quizzes/{quiz_id}/attempt` | Required | Submit quiz attempt |
| `GET` | `/assessment/quizzes/{quiz_id}/attempts` | Required | Get my attempt history |

### Certificates — Generation & Verification (4 endpoints)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/certificates/enrollments/{enrollment_id}/generate` | Required | Generate certificate |
| `GET` | `/certificates/me` | Required | List my certificates |
| `GET` | `/certificates/verify/{qr_code}` | **None** | Public QR verification |
| `GET` | `/certificates/{certificate_id}` | Required | Get certificate by ID |

### Health (1 endpoint)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness probe |

**Total: 34 endpoints.**

---

## Swagger / OpenAPI Docs

Interactive API documentation is available at two URLs when the service is running:

| URL | Description |
|-----|-------------|
| `GET /docs` | **Swagger UI** — interactive playground to test endpoints directly from the browser. Click "Authorize" to paste your JWT Bearer token. |
| `GET /redoc` | **ReDoc** — clean, readable API documentation. Better for sharing with frontend teams. |

### How to use Swagger UI

1. Start the service (see [Running Locally](#running-locally))
2. Open `http://localhost:8002/docs` in your browser
3. Click the **"Authorize"** button (top right)
4. Enter: `Bearer <your-jwt-token>`
5. Browse endpoints by tag: **LMS**, **Assessment**, **Certificates**
6. Click "Try it out" on any endpoint to send a real request
7. View request/response schemas inline

### Tags in Swagger

| Tag | Endpoints | Description |
|-----|-----------|-------------|
| LMS | 22 | Course, module, lesson CRUD + enrollment + progress |
| Assessment | 7 | Quiz management + attempt submission + grading |
| Certificates | 4 | Certificate generation + public QR verification |
| Health | 1 | Liveness probe |

---

## Configuration

All settings are loaded from environment variables via `app/config.py` (Pydantic `BaseSettings`).

| Variable | Required | Description |
|----------|----------|-------------|
| `COURSE_DATABASE_URL` | Yes | PostgreSQL async DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | Redis DSN (`redis://...`) |
| `JWT_SECRET` | Yes | Shared HS256 secret (must match identity service) |
| `ENV_NAME` | No | `development` / `staging` / `production` |
| `CORS_ORIGINS` | No | JSON array or comma-separated list of allowed origins |

---

## Running Locally

```bash
# 1. Install dependencies (from repo root)
pip install -r services/course/requirements.txt

# 2. Set environment variables
export COURSE_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/course_db
export REDIS_URL=redis://localhost:6379
export JWT_SECRET=dev-secret

# 3. Apply migrations
cd migrations/course
alembic upgrade head

# 4. Start the service
cd services/course
uvicorn app.main:app --reload --port 8002
```

Swagger UI will be available at `http://localhost:8002/docs`.

---

## Database Migrations

Migration files live in `migrations/course/alembic/versions/`.

| Revision | Description |
|----------|-------------|
| `001_initial_course` | Initial placeholder |
| `856d8eddef4e` | Full schema: courses, course_modules, lessons, quizzes, enrollments, lesson_progress, certificates |

To create a new migration:

```bash
cd migrations/course
alembic revision --autogenerate -m "describe_the_change"
alembic upgrade head
```

---

## External Service Dependencies

This service uses **soft foreign keys** (UUIDs only, no DB-level FK to other services).

### 1. Identity Service (critical)

- **JWT tokens** — validates HS256 tokens, reads `payload["sub"]` as user UUID.
- **Instructor identity** — `instructor_id` on courses is a soft reference.
  Frontend should hydrate instructor name/avatar from identity service.

### 2. Payment Service — MS-6 (for paid enrollment)

- **Payment verification** — `payment_id` passed during paid enrollment is a soft
  reference. In production, MS-3 should verify payment status with MS-6 before
  creating enrollment.
- **Reconciliation** — A background job should periodically query MS-6 for
  successful payments and create any missing enrollments.
- **Refunds** — Refund eligibility (<20% progress, within 7 days) is checked by
  MS-3. Actual refund processing is handled by MS-6.

### 3. Notification Service — MS-7 (not wired yet)

Events that should trigger notifications:

| Event | Expected notification |
|-------|-----------------------|
| Enrollment created | "You've enrolled in {course_title}" |
| Course completed | "Congratulations! You've completed {course_title}" |
| Certificate issued | "Your certificate for {course_title} is ready" |
| Quiz passed | "You passed {quiz_title} with {score}%" |

### 4. API Gateway (assumed present)

- Admin role gating for course management endpoints
- Rate limiting at gateway level
- Token refresh flows

---

## Known Gaps & Future Work

| # | Gap | Priority | Notes |
|---|-----|----------|-------|
| 1 | PDF certificate generation | High | Currently returns placeholder URL. Needs S3 + PDF template engine. |
| 2 | Payment verification on enrollment | High | Should call MS-6 to verify payment_id before creating enrollment |
| 3 | Reconciliation background job | High | Periodic job to catch missed payment→enrollment events |
| 4 | Notification events | Medium | Fire events to MS-7 on enrollment, completion, certificate |
| 5 | SCORM package runtime | Medium | `scorm_package_url` stored but no SCORM player/wrapper yet |
| 6 | Video streaming integration | Medium | `content_url` stored but no signed URL generation or DRM |
| 7 | Course ratings/reviews | Medium | `rating_avg` column exists but no review submission endpoint |
| 8 | Instructor analytics dashboard | Low | Enrollment stats, completion rates, quiz performance |
| 9 | Bulk lesson import | Low | CSV/Excel upload for course content creation |
| 10 | Course search indexing to OpenSearch | Low | Push course data to content_index for unified search |
| 11 | Refund processing integration | Low | Eligibility check exists; actual refund goes through MS-6 |
| 12 | Admin RBAC | Low | Currently delegated to API gateway |

---

*Last updated: 2026-02-20*
