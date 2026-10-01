#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen --extra dev --extra local
npm ci --prefix frontend
npm run build --prefix frontend
uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn voxdesk.main:app --host 127.0.0.1 --port 8000 --no-access-log
