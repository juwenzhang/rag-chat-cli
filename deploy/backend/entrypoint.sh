#!/usr/bin/env sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[backend] running database migrations"
  uv run alembic upgrade head
fi

echo "[backend] starting application"
exec "$@"
