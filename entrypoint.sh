#!/bin/sh
set -e

echo "⏳ Waiting for database to be ready..."

# Wait until Postgres is reachable
until alembic upgrade head
do
  echo "⏳ Database not ready yet, retrying..."
  sleep 3
done

echo "✅ Database is ready & migrations applied"

echo "DATABASE_URL=$DATABASE_URL"

echo "🚀 Starting FastAPI app..."
exec "$@"
