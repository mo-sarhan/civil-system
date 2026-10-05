# syntax=docker/dockerfile:1
#
# Backend image: FastAPI + uvicorn.
# Layered so dependency installation is cached until requirements change.

# ---------------------------------------------------------------------------
# Builder: compile wheels once, with the toolchain we throw away afterwards.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY backend/requirements.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Africa/Cairo \
    IMPORT_STORAGE_DIR=/data/uploads

# libpq for psycopg, curl for the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl tzdata \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user: the API never needs root.
RUN groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY backend/requirements.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=app:app backend/app ./app
COPY --chown=app:app backend/alembic ./alembic
COPY --chown=app:app backend/scripts ./scripts
RUN chmod +x /app/scripts/entrypoint.sh
COPY --chown=app:app backend/alembic.ini backend/pyproject.toml ./
# Kept in the image so `seed --sample` works without a bind mount.
COPY --chown=app:app sample_civil_registry.sql ./sample_civil_registry.sql

# Import uploads must survive container restarts: mount a volume here.
RUN mkdir -p /data/uploads && chown -R app:app /data/uploads

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]