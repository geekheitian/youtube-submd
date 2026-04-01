#!/bin/bash
set -e

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/youtube_submd}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export YTSUBMD_ENV="${YTSUBMD_ENV:-development}"

echo "Starting API server..."
echo "DATABASE_URL: ${DATABASE_URL}"
echo "REDIS_URL: ${REDIS_URL}"
echo "YTSUBMD_ENV: ${YTSUBMD_ENV}"

uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
