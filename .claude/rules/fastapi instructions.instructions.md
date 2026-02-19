---
description: FastAPI backend architecture and best practices for Docfliq
paths:
  - "**/*.py"
---
1. Writing Principles
General Code Philosophy
Write concise, technical Python. Every function must have complete type hints for parameters and return values.
Prefer functional and declarative patterns. Use classes only for data models (Pydantic, SQLAlchemy, Beanie) and services with injectable state.
Follow the RORO pattern — Receive an Object, Return an Object. Accept Pydantic models, return Pydantic models.
Apply DRY rigorously. If logic appears twice, extract it into a utility or dependency.
Use descriptive names with auxiliary verbs: is_active, has_permission, can_edit, should_notify.
All files and directories use lowercase with underscores: user_service.py, auth_router.py.
Function Writing Rules
Handle errors and edge cases FIRST using guard clauses and early returns.
Place the happy path LAST in every function.
Avoid deeply nested if/else. Use if-return pattern instead.
Each function should do ONE thing. If a function name has "and" in it, split it.
Keep functions under 30 lines. If longer, decompose into smaller helpers.
Pure business logic functions should have ZERO framework imports — no FastAPI, no SQLAlchemy inside service functions where possible.
Async Rules
Use async def for any function that performs I/O: database queries, Redis calls, HTTP requests, file operations.
Use def (sync) only for pure CPU-bound computation with no I/O whatsoever.
Never perform blocking operations inside an async def function — this freezes the entire event loop and blocks ALL concurrent requests.
If you must call a synchronous/blocking library from async code, offload it to a thread executor.
All database drivers, HTTP clients, and cache clients must be their async variants.
Pydantic Rules (V2 Only)
Always use Pydantic V2 syntax. Never use V1 patterns like class Config, .dict(), .json(), or orm_mode.
Use model_config = ConfigDict(...) for model configuration. Use from_attributes=True for ORM compatibility.
Use .model_dump() and .model_dump_json() — never the deprecated V1 equivalents.
Create a shared custom base model with common config (whitespace stripping, min length, etc.) and inherit all schemas from it.
Separate request schemas (Create, Update) from response schemas. Never reuse the same schema for both input and output.
Use Field() for all validation constraints. Use EmailStr for emails. Use Annotated types for reusable field definitions.
Never return raw dictionaries from endpoints. Always declare a response_model or return type annotation with a Pydantic model.
Dependency Injection Rules
Use FastAPI's Depends() for all shared resources: database sessions, Redis connections, current user, permissions.
Chain dependencies logically: require_admin → depends on get_current_user → depends on oauth2_scheme.
Dependencies are cached per-request — calling Depends(get_current_user) multiple times in the same request only executes it once.
Use dependencies for validation beyond Pydantic: checking database uniqueness, verifying resource existence, enforcing ownership.
Prefer async dependencies over sync ones.
Use Annotated type aliases to reduce repetitive Depends() boilerplate in route signatures.
Configuration Rules
Use pydantic-settings with BaseSettings for all configuration. Load from .env files.
Never hardcode secrets, database URLs, API keys, or environment-specific values.
Create a single settings instance and import it — do not re-instantiate.
Separate settings by concern if needed: DatabaseSettings, AuthSettings, RedisSettings.
Always provide a .env.example with placeholder values in version control.
Lifecycle Rules
Never use the deprecated @app.on_event("startup") or @app.on_event("shutdown") decorators.
Always use the lifespan async context manager for startup/shutdown logic.
Initialize all database connections, ODM engines, and cache pools in the lifespan startup phase.
Dispose all connections and pools in the lifespan shutdown phase.

2. Project Structure
Use domain-driven modular layout. Group files by feature/domain, not by technical type.
project-root/
├── alembic/                        # Database migrations (PostgreSQL)
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # App creation, lifespan, router registration, middleware
│   ├── config.py                   # Global settings (BaseSettings from pydantic-settings)
│   ├── database.py                 # All DB engines: Postgres session, Mongo init, Redis pool
│   ├── dependencies.py             # Shared global dependencies (get_db, get_redis, etc.)
│   ├── exceptions.py               # Base exception classes used across all domains
│   ├── models.py                   # SQLAlchemy DeclarativeBase, shared mixins (timestamps, soft-delete)
│   ├── pagination.py               # Shared pagination request/response logic
│   ├── utils.py                    # Cross-cutting utilities (slugify, date formatting, etc.)
│   │
│   ├── auth/                       # ── Auth Domain ──
│   │   ├── __init__.py
│   │   ├── router.py               # All route definitions for /auth
│   │   ├── controller.py           # Request handling — calls services, maps responses
│   │   ├── service.py              # Pure business logic — no framework imports
│   │   ├── schemas.py              # Pydantic V2 request/response models
│   │   ├── models.py               # SQLAlchemy tables or Beanie documents
│   │   ├── dependencies.py         # get_current_user, require_role, token validation
│   │   ├── constants.py            # Enums, error codes, token expiry values
│   │   ├── config.py               # Domain-specific env vars (JWT_SECRET, etc.)
│   │   ├── exceptions.py           # InvalidCredentials, TokenExpired, etc.
│   │   └── utils.py                # Password hashing, token creation helpers
│   │
│   ├── users/                      # ── Users Domain (same pattern) ──
│   ├── posts/                      # ── Posts Domain ──
│   └── notifications/              # ── Notifications Domain ──
│
├── tests/
│   ├── conftest.py                 # Async fixtures, test DB setup, test Redis, overrides
│   ├── factories.py                # Test data factories
│   ├── auth/
│   │   ├── test_router.py
│   │   └── test_service.py
│   ├── users/
│   └── posts/
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml                  # Deps + Ruff config + pytest config
├── alembic.ini
├── .env.example
└── .gitignore
File Responsibilities
File
Role
Rules
router.py
Route definitions only
Declare endpoints, apply dependencies, set response models. Zero business logic. Delegates to controller.
controller.py
Request orchestration
Receives validated input from router, calls service functions, composes the response. Thin glue layer between HTTP and business logic.
service.py
Pure business logic
No FastAPI imports, no database driver imports. Receives data objects and session/client via parameters. Fully testable in isolation.
schemas.py
Pydantic models
Request models (Create/Update), response models, query parameter models. Separate input from output.
models.py
Database models
SQLAlchemy ORM classes (PostgreSQL) or Beanie Document classes (MongoDB). One file per domain.
dependencies.py
Dependency providers
Functions used with Depends() — auth checks, permission guards, resource loaders.
constants.py
Static values
Enums, error code mappings, config constants. No logic.
config.py
Domain settings
Domain-specific BaseSettings subclass for env vars relevant to this feature.
exceptions.py
Custom errors
Domain-specific HTTPException subclasses with preset status codes and messages.
utils.py
Helpers
Stateless helper functions — formatting, hashing, encoding. No business logic, no framework dependencies.

Layer Flow
Request → router.py → controller.py → service.py → database (models.py)
                                            ↓
Response ← router.py ← controller.py ← service.py
Router knows about HTTP (methods, status codes, response models, dependencies).
Controller knows about request/response mapping and calling the right services.
Service knows only about business rules and data. It is framework-agnostic.
Models define the data shape in the database.
Schemas define the data shape over the wire (API contracts).
Cross-Module Import Rules
Always use absolute imports with explicit module names: from src.auth import constants as auth_constants.
Never use relative imports across domain boundaries.
If module A frequently imports from module B, consider whether they should be merged or a shared module extracted.
Circular imports usually mean your domain boundaries are wrong — refactor.
main.py Responsibilities (Keep It Thin)
Create the FastAPI app instance with metadata (title, version, docs URL).
Define the lifespan context manager for startup/shutdown.
Register all routers with versioned prefixes (/api/v1/...).
Add middleware (CORS, logging, gzip).
Add global exception handlers.
Nothing else — no business logic, no model definitions, no utility functions.

3. Database Query Optimizations
PostgreSQL (Async SQLAlchemy 2.0)
Always use SQLAlchemy 2.0-style queries with select(), insert(), update(), delete() — never the legacy session.query() pattern.
Always use the async engine and async sessions. Never use synchronous engine in an async app.
Use asyncpg as the driver — it is significantly faster than sync alternatives in async contexts.
Set expire_on_commit=False on the session maker to prevent lazy-load issues after commit.
Enable pool_pre_ping=True on the engine to detect and recycle stale connections.
Query-Level Optimizations:
N+1 Query Problem: The most common performance killer. If you load a list of N parent records and then access a relationship on each one, the ORM fires N additional queries (1 for the list + N for each child). Always use eager loading strategies (selectinload(), joinedload(), subqueryload()) to fetch related data in a single query or a predictable number of queries. Profile with echo=True in development to spot N+1 patterns — if you see the same SELECT repeating per row, you have an N+1 problem.
Use selectinload() or joinedload() for eager loading relationships. Never rely on lazy loading in async code — it causes implicit I/O and will raise errors.
Use .limit() and .offset() or keyset pagination for list queries. Never fetch unbounded result sets.
Use .where() conditions that target indexed columns. Avoid full table scans.
Select only the columns you need instead of loading full ORM objects when a few fields suffice.
Use flush() instead of commit() when you need generated IDs mid-transaction without ending the transaction.
Batch inserts using bulk methods — never insert in a loop with individual commits.
Use database-level indexes for all columns that appear in WHERE, ORDER BY, or JOIN clauses.
Use database-side count functions instead of fetching rows and counting in Python.
Set naming conventions on the metadata for predictable constraint names across migrations.
Connection Pool Tuning:
Configure pool_size and max_overflow based on expected concurrent load.
In production, size the pool to roughly match the number of concurrent request-handling tasks.
Use pool_recycle (e.g., 3600 seconds) to prevent connections from going stale.
MongoDB (Beanie ODM)
Define indexes using Beanie's indexed type on fields that are frequently queried or sorted.
Use projection to fetch only needed fields instead of loading entire documents.
Use skip() and limit() for pagination. For large datasets, prefer range-based pagination over skip-based.
Use Beanie's query filters rather than fetching all documents and filtering in Python.
N+1 in MongoDB: If you fetch a list of documents and then make individual queries per document to resolve references or related data, you have the same N+1 problem. Use aggregation pipelines with $lookup to join related collections in a single query, or embed related data directly in the document where read patterns justify it.
For complex aggregations, access the underlying Motor collection and run native aggregation pipelines.
Avoid fetching large lists of documents into memory. Always set a reasonable upper bound on list operations.
Batch writes using bulk insert instead of individual inserts in a loop.
Create compound indexes for queries that filter on multiple fields together.
Redis
Always set TTL (expiration) on cached values. Never cache without an expiry.
Use key prefixes consistently for namespacing: user:{id}, cache:post:{slug}, session:{token}.
Use batch commands (multi-get, multi-set) instead of individual commands in a loop.
Use pipelining for multiple commands that don't depend on each other's results.
Serialize Pydantic models using their built-in JSON methods — avoid manual dict conversion.
Invalidate cache explicitly on any write operation (create/update/delete). Stale cache is worse than no cache.
For frequently accessed but rarely changed data, use longer TTLs. For volatile data, use short TTLs.
Use Redis hashes for structured objects instead of serializing entire JSON blobs when you need partial reads/writes.
Monitor cache hit rates. A cache that's never hit is wasted memory and added complexity.
General Database Principles
Never mix sync and async database drivers in the same application.
Always use connection pooling. Opening a new connection per request is extremely expensive.
Keep transactions as short as possible. Avoid holding a transaction open while waiting on external HTTP calls.
Use read replicas for heavy read queries if available.
Log slow queries in development, silence them in production.
Use database migrations (Alembic) for all PostgreSQL schema changes. Never use create_all() in production.
Keep migration files in version control and review auto-generated migrations before applying.

4. Common Pitfalls
Async/Blocking Mistakes
Calling blocking functions (sleep, synchronous HTTP, sync file I/O) inside an async def route. This blocks the event loop and halts ALL concurrent request processing.
Using synchronous database drivers in an async FastAPI application. Always use their async counterparts.
Forgetting to await async function calls. This silently returns a coroutine object instead of the actual result.
Defining a route as async def but only doing sync/CPU work inside. Use plain def instead — FastAPI runs it in a threadpool automatically.
SQLAlchemy Mistakes
Using session.query(Model) — this is 1.x style. Always use select(Model) with session.execute().
Using create_engine() instead of create_async_engine() in async applications.
Relying on lazy loading in async code. Lazy-loaded relationships trigger implicit sync I/O and will raise exceptions. Always use eager loading.
Not detecting N+1 queries. Enable echo=True on the engine during development and watch for repeated SELECT statements — that's N+1. Fix by adding selectinload() or joinedload() options to the query.
Forgetting to import all model files in Alembic's env.py. Alembic can only detect imported models.
Using Base.metadata.create_all() in production instead of proper Alembic migrations.
Not setting expire_on_commit=False — causes detached instance errors after commit.
Pydantic Mistakes
Using Pydantic V1 patterns: class Config:, .dict(), .json(), orm_mode = True. All deprecated in V2.
Using the same Pydantic model for both request input and response output. Always separate them — input models may have passwords or write-only fields.
Returning raw dictionaries instead of Pydantic models from endpoints. You lose validation, documentation, and serialization control.
Not setting response_model on endpoints — OpenAPI docs won't show the response schema.
MongoDB/Beanie Mistakes
Not passing document models to the ODM initialization at startup. Collections won't be set up.
Fetching entire collections into memory without limits. MongoDB will happily return millions of documents.
Not defining indexes on frequently queried fields. This leads to full collection scans.
Redis Mistakes
Caching without TTL. Stale data accumulates and memory grows unbounded.
Not invalidating cache on writes. Users see outdated data after updates.
Using decode mode globally when some operations need binary data.
Caching too aggressively early on. Add caching only where you've measured a performance problem.
Middleware Mistakes
Middleware order matters. Middleware executes in reverse registration order (last registered runs first on request). Placing CORS middleware after custom auth middleware can cause preflight requests to fail silently.
Not adding error handling inside custom middleware. If middleware calls call_next(request) without a try/except, an unhandled exception in a route will crash the middleware chain instead of returning a proper error response.
Adding too many middleware layers. Each middleware adds a coroutine boundary and overhead on every single request. Profile before adding middleware — some logic belongs in dependencies, not middleware.
Dependency Injection Mistakes
Recreating database engines or session factories inside dependencies or endpoints. Initialize once at startup (in lifespan), reuse throughout the application lifecycle via dependency injection.
Using sync dependencies for trivial non-I/O operations. Sync dependencies run in a threadpool, which has overhead. For simple validation or value computation, use async dependencies even if there's nothing to await.
Deep dependency trees with many levels of chaining. Each level adds resolution overhead. Keep dependency chains shallow (2-3 levels max).
Not understanding dependency scoping. By default, FastAPI creates a new instance per request. If a dependency is expensive, consider caching it at app scope (via lifespan/app.state) rather than recreating per request.
Defining dependencies with side effects at global/module scope. Dependencies should be lazily resolved, not eagerly executed on import.
WebSocket Mistakes
Not properly closing WebSocket connections. Always use try/finally blocks to ensure connections are closed on error or disconnect. Leaked connections consume memory and file descriptors.
Not handling WebSocket disconnect exceptions. Clients can disconnect at any time — your handler must catch WebSocketDisconnect to avoid unhandled exception logs.
Memory & Resource Mistakes
Memory growth (apparent leaks) in long-running async FastAPI services due to memory fragmentation. Async servers interleave allocations from concurrent requests, preventing the allocator from reclaiming memory. Consider using jemalloc as an alternative allocator in production containers.
Large file uploads without streaming. Reading entire file uploads into memory can exhaust server RAM. Use streaming/chunked reads for large files.
Not closing or disposing of HTTP client sessions (httpx, aiohttp) after use. Unclosed clients leak connections and sockets.
Deployment Mistakes (continued)
Using --reload flag in production. It's for development only — it restarts the server on every file change and adds file-watching overhead.
Not setting request timeouts. Without timeouts, a slow downstream service can hold connections indefinitely, exhausting the connection pool.
Misconfiguring docs_url or openapi_url — overriding them incorrectly disables Swagger UI and breaks API documentation.
Security Mistakes
Using allow_origins=["*"] in CORS middleware in production. Always specify exact allowed origins.
Not using parameterized queries. Even with an ORM, raw SQL with f-strings is a SQL injection risk. Always use ORM query builders or bound parameters.
Storing passwords in plain text or with weak hashing (MD5, SHA1). Use Argon2 or bcrypt.
Not validating or constraining input lengths and formats via Pydantic. Unbounded string inputs can be used for denial-of-service or injection attacks.
Exposing /docs and /redoc in production without authentication. Disable or restrict access to API documentation in deployed environments.
Not implementing rate limiting. Unthrottled APIs are vulnerable to brute-force and denial-of-service attacks.
Serialization & Response Mistakes
FastAPI creates the response Pydantic model TWICE when you return a Pydantic object with response_model set — once when you create it, and again when FastAPI validates it against the response_model via jsonable_encoder. Be aware of the overhead on expensive model validators.
Using orjson or ujson response classes without understanding their tradeoffs. Standard JSONResponse is safest; switch to ORJSONResponse only when you've profiled and confirmed JSON serialization is a bottleneck.
Deeply nested Pydantic schemas cause significant serialization overhead. Flatten response schemas where possible for performance-critical endpoints.
Raising HTTPException inside Pydantic @field_validator — this returns a 500 instead of 422. Raise ValueError or use Pydantic's built-in constraints instead.
Background Task Mistakes
Using asyncio.create_task() inside route handlers without retaining references. Orphaned tasks can be garbage collected, silently dropped, or cause resource leaks.
Using background tasks for operations critical to the response. If the result matters to the client, await it — don't background it.
Using BackgroundTasks for heavy, long-running jobs. FastAPI's BackgroundTasks runs in the same process. For heavy work, use a proper task queue (Celery, Dramatiq, Arq).
Deployment Mistakes
Running Uvicorn with a single worker in production. Use multiple workers via Gunicorn (gunicorn -k uvicorn.workers.UvicornWorker -w 4) to utilize multiple CPU cores.
Not placing a reverse proxy (Nginx, Traefik) in front of Uvicorn. The reverse proxy handles SSL termination, static files, load balancing, and request buffering.
Spinning up multiple workers with heavy in-memory objects (ML models, large caches). Each worker is a separate process — memory is duplicated per worker.
Not installing uvloop and httptools in production. These drop-in replacements for asyncio's event loop and HTTP parser significantly improve throughput with zero code changes.
API Design Mistakes
Returning bare lists from list endpoints without an envelope/wrapper. Once clients depend on a bare array, you cannot add pagination metadata (total, next_cursor, has_more) without a breaking change. Always wrap list responses in an object from day one.
Using offset-based pagination with large skip values. Database performance degrades as offset grows. For large datasets, use cursor/keyset pagination instead.
Not validating pagination parameters. Allow negative page numbers or absurdly large page sizes and you invite abuse. Constrain with Pydantic Field(ge=1, le=100).
Mixing naive and timezone-aware datetimes. Always use timezone-aware datetimes (UTC) throughout the application. Naive datetimes cause silent bugs when serializing or comparing across timezones.
Using floats for money/currency. Floating point precision drift causes rounding errors. Use integer minor units (cents) or Decimal with explicit precision.
Not documenting streaming responses properly. StreamingResponse and SSE endpoints do not auto-generate response schemas in OpenAPI. Add manual documentation via responses parameter.
No consistent error envelope. Without a standardized error response shape across all endpoints, frontend clients have to special-case error parsing. Define a global error schema and use it everywhere.
Response Handling Mistakes
Returning a Response object directly bypasses FastAPI's validation and serialization entirely. The response_model is ignored, no filtering happens, and OpenAPI docs will not reflect the actual data. Only use direct Response when you intentionally need to skip all processing.
FastAPI runs jsonable_encoder on every response by default to ensure JSON serializability. For large payloads where you know the data is already JSON-safe, returning via ORJSONResponse or Response directly avoids this overhead. Note that jsonable_encoder is sync and CPU-bound — on large payloads it can stall the event loop.
Not using response_model_exclude_unset=True when you want PATCH-style responses that omit fields the client did not send. Without it, all fields including defaults are returned.
Setting default_response_class=ORJSONResponse on the app but still returning dicts or Pydantic models from endpoints. FastAPI will still run jsonable_encoder before passing to ORJSONResponse. To get the performance benefit, you must return ORJSONResponse(content=...) directly.
Embedding binary data (files, images) in JSON responses. Use StreamingResponse or FileResponse for binary payloads. Response models are for JSON-shaped data contracts only.
Logging & Observability Mistakes
Using print() instead of proper structured logging. Print statements are not filterable, not leveled, and get lost in production.
Not including request/correlation IDs in logs. Without a unique ID per request, tracing a single request across log lines is nearly impossible. Use middleware to generate and attach a UUID to every request.
Logging sensitive data (passwords, tokens, PII, full request bodies with credentials). Scrub or mask sensitive fields before logging.
Not separating access logs from application logs. They serve different purposes and should be configurable independently.
Using blocking file I/O handlers for logging in async applications. Use QueueHandler or async-safe logging libraries to avoid stalling the event loop.
No health check endpoint. Load balancers, Kubernetes, and monitoring systems need a lightweight /health endpoint. It should not hit the database unless you want a deep health check.
Not adding request timing middleware. Without tracking how long each endpoint takes, you cannot identify slow routes in production. Add simple timing middleware from the start.
CORS-Specific Mistakes
CORS middleware must be the FIRST middleware added. If auth middleware runs before CORS middleware, preflight OPTIONS requests will get 401 errors because they do not carry auth tokens. The browser then shows a CORS error instead of the actual 401.
Using allow_origins=["*"] with allow_credentials=True simultaneously. Browsers reject this combination — you cannot use wildcard origins when credentials are enabled. List specific origins explicitly.
Not setting max_age on CORS middleware. Without it, browsers send a preflight OPTIONS request before every single non-simple request, adding latency. Set a reasonable cache duration (e.g., 600 seconds).
Returning error responses from custom middleware without CORS headers. If your middleware returns a 401/403 before the request reaches CORS middleware, the response will lack CORS headers and the browser will show a CORS error instead of the actual error.
Testing Mistakes
Not using TestClient as a context manager (with TestClient(app) as client:). Without the context manager, lifespan events (startup/shutdown) do not execute, so dependencies initialized in lifespan are missing during tests.
Using a production database for tests. Always use a separate test database or in-memory database. Use fixtures that create/drop tables per test session.
Not testing error paths and edge cases. Only testing happy paths misses validation errors, auth failures, rate limits, and missing resources.
Tests that depend on execution order or share mutable state. Each test must be fully independent. Use fresh fixtures per test.
Not testing with async. If your app uses async dependencies and async database sessions, your tests should use pytest-asyncio and httpx.AsyncClient for realistic coverage.
Forgetting to mock external services in tests. Tests that hit real external APIs are slow, flaky, and can fail due to network issues.
Architecture Mistakes
Putting business logic in routers. Routers should only handle HTTP concerns. Logic belongs in services.
One endpoint calling another endpoint internally. This adds unnecessary HTTP overhead (serialization, auth, logging). Extract shared logic into a service function instead.
Using mutable global variables for shared state across async requests. This causes race conditions. Use dependency injection, databases, or Redis for shared state.
Hardcoding configuration values instead of using environment variables with settings management.
Using deprecated startup/shutdown event decorators instead of the lifespan context manager.
Relative imports across domain boundaries — leads to circular imports and tight coupling.
Not using API versioning from the start. Always prefix routes with /api/v1/.
Exposing internal error details (stack traces, SQL queries, file paths) in production error responses.
Skipping type hints. FastAPI's validation, documentation, and IDE support all rely on them.
Not using a global exception handler. Unhandled exceptions return unhelpful 500 errors.
Over-engineering from day one. Start simple, refactor to domain-driven when complexity demands it.
Not handling graceful shutdown. Without proper signal handling and connection draining in the lifespan shutdown phase, in-flight requests get killed mid-execution during deployments.

