#!/bin/bash
set -e

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/youtube_submd}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export YTSUBMD_ENV="${YTSUBMD_ENV:-development}"

echo "Starting Celery worker..."
echo "DATABASE_URL: ${DATABASE_URL}"
echo "REDIS_URL: ${REDIS_URL}"
echo "YTSUBMD_ENV: ${YTSUBMD_ENV}"

celery -A workers.celery_app worker --loglevel=INFO -Q youtube-submd
