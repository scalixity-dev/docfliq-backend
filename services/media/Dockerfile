# ─────────────────────────────────────────────────────────────────────────────
# Docfliq Media Service (MS-5) — API + Worker image
#
# Build from repo root:
#   docker build -f services/media/Dockerfile -t docfliq-media .
#
# Runs as API (default) or Worker (set ROLE=worker env var).
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# System deps for Pillow, asyncpg, and healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libjpeg62-turbo-dev libwebp-dev zlib1g-dev \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies ──────────────────────────────────────────────
COPY shared/ /app/shared/
COPY services/media/pyproject.toml services/media/requirements.txt /app/services/media/

RUN pip install --no-cache-dir -e /app/shared && \
    pip install --no-cache-dir \
        "fastapi>=0.109" \
        "uvicorn[standard]>=0.27" \
        "pydantic[email]>=2.5" \
        "pydantic-settings>=2.1" \
        "sqlalchemy[asyncio]>=2.0" \
        "asyncpg>=0.29" \
        "redis>=5.0" \
        "arq>=0.26" \
        "python-jose[cryptography]>=3.3" \
        "slowapi>=0.1.9" \
        "aioboto3>=13.0" \
        "Pillow>=10.0"

# ── Copy application code ────────────────────────────────────────────────────
COPY services/media/app/ /app/services/media/app/

ENV PYTHONPATH=/app:/app/services/media
WORKDIR /app/services/media

# ── Entrypoint — ROLE env decides API or Worker ──────────────────────────────
COPY services/media/entrypoint.sh /app/services/media/entrypoint.sh
RUN chmod +x /app/services/media/entrypoint.sh

EXPOSE 8005

ENTRYPOINT ["/app/services/media/entrypoint.sh"]
