#!/bin/sh
# Container entrypoint: apply migrations, then serve the API.
#
# `AUTO_MIGRATE=false` disables the migration step for deployments that run
# Alembic separately (CI, blue/green cutovers, or several replicas racing).
set -eu

if [ "${AUTO_MIGRATE:-true}" = "true" ]; then
    echo "[entrypoint] applying database migrations"
    alembic upgrade head
fi

echo "[entrypoint] starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"