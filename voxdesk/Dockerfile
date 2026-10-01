FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /uvx /usr/local/bin/
RUN apt-get update && apt-get install --no-install-recommends -y ffmpeg espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 voxdesk
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 DATABASE_URL=sqlite+aiosqlite:////data/voxdesk.db HF_HOME=/home/voxdesk/.cache/huggingface
COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev --extra local
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY --from=web /web/dist ./frontend/dist
RUN mkdir -p /data /home/voxdesk/.cache && chown -R voxdesk:voxdesk /data /home/voxdesk/.cache
USER voxdesk
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live',timeout=3)"]
CMD ["/app/.venv/bin/uvicorn", "voxdesk.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
