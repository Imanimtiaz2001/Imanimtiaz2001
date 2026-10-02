FROM node:22-bookworm-slim AS web
WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 clearcv && useradd --uid 10001 --gid clearcv --create-home clearcv
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps . && mkdir -p /app/data && chown -R clearcv:clearcv /app
COPY --from=web --chown=10001:10001 /build/web/dist/ ./web/dist/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)"
CMD ["uvicorn", "clearcv.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
