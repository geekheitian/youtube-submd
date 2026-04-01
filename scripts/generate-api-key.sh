#!/bin/bash
set -e

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:5432/youtube_submd}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export YTSUBMD_ENV="${YTSUBMD_ENV:-development}"

echo "Generating API key..."
python3 -c "
import sys
sys.path.insert(0, '.')
from storage.keys import generate_api_key

raw, key_hash, key_prefix = generate_api_key()
print()
print('=' * 60)
print('NEW API KEY GENERATED')
print('=' * 60)
print(f'Prefix: {key_prefix}****')
print(f'Full key: {raw}')
print()
print('IMPORTANT: Save this key now. The full value cannot be recovered.')
print('=' * 60)
"
