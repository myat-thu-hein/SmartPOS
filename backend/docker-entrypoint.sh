#!/bin/sh
# Container entrypoint: optional migrations and development demo data, then the server.
set -eu

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "Applying database migrations..."
  alembic upgrade head
fi

if [ "${SEED_DEMO:-false}" = "true" ]; then
  # The seed refuses to run when APP_ENV=production and skips an existing demo restaurant.
  echo "Seeding development demo data..."
  python -m app.seed.demo
fi

exec "$@"
