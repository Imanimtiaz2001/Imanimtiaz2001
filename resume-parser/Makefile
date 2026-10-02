.PHONY: install dev build test evaluate serve
install:
	uv sync --extra dev --frozen
	cd web && npm ci
build:
	cd web && npm run build
serve:
	uv run --frozen uvicorn clearcv.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Use separate terminals for backend and frontend hot reload.
dev:
	uv run --frozen uvicorn clearcv.main:app --host 127.0.0.1 --reload --no-access-log
test:
	uv run --frozen --extra dev ruff check src tests scripts
	uv run --frozen --extra dev ruff format --check src tests scripts
	uv run --frozen --extra dev pytest
	cd web && npm run build
evaluate:
	uv run --frozen python scripts/evaluate.py
