# Operating ClearCV

## Local team scope
Compose publishes only `127.0.0.1:8000`. One shared operator key grants access to every record; records are not separated by user. Set a random 32-byte secret (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) in `CLEARCV_API_KEY` before a shared deployment. Keep the key in `.env` or a secrets manager. Use HTTPS and an authenticated reverse proxy if expanding beyond localhost. The browser keeps the operator key in memory, never localStorage or the URL.

## Data lifecycle
PDF uploads are bounded, read in memory, processed in an isolated worker and not saved as source files. Multipart temporary files are explicitly closed. OCR images live in a temporary directory removed on success/error; after a forced worker termination, the host's temporary-file lifecycle is the fallback, so keep container `/tmp` ephemeral. Source text and extraction results contain candidate personal data and are stored in the database. They expire after `CLEARCV_RETENTION_HOURS` (default 24); expired records are hidden immediately and physically purged every minute while the app runs, and on restart. Delete removes the live DB record. Database backups, exported files and database WAL are governed separately; deletion is not a secure erase of those copies. Encrypt volumes/backups and define a backup retention policy for real candidate data.

OpenAI mode sends extracted text to OpenAI after per-upload consent. `store=false` disables Responses API application storage; it is not a guarantee about every provider retention mechanism. Review the provider's current data policy before handling real resumes. No PDF bytes are sent to the model. Provider credentials, request bodies, names and filenames are excluded from application request logs and metric labels. Run Uvicorn with `--no-access-log`; infrastructure logs are outside this application policy.

## Limits and capacity
Default bounds: 10 MB files, 10 pages, 60,000 extracted characters, 3,000 lines, 12 million OCR pixels per page, 20 seconds per Tesseract invocation, 60 seconds per PDF worker, 40 seconds total LLM stage, 2 active parse workers. At most twice the parser capacity buffers upload requests; extra requests return 429. Multipart overhead has a separate 1 MB allowance. File bytes are checked again after multipart parsing, including chunked requests. Upload receiving has a 20-second deadline. No file names are used as paths.

The API uses one process per container so limits and Prometheus metrics are coherent. Multiple replicas require ingress limits and aggregate metrics. A growing workload needs a bounded durable job queue rather than long synchronous HTTP requests; do not add arbitrary Uvicorn workers and assume the current global limits stay global.

## Health and troubleshooting
- `/health/live`: process responds. `/health/ready`: database connectivity.
- `/api/metrics`: parse outcome counters and latency histogram, protected by operator key.
- `encrypted_pdf`: export an unlocked document.
- `ocr_failed`: install the configured Tesseract language packs.
- `too_much_text` or `page_dimensions`: export a normal-size resume rather than raising bounds blindly.
- `unsupported_evidence`: model output cited unsupported content; nothing was saved.
- `provider_invalid/incomplete/refusal/error/timeout`: no partial result saved; check server credentials/model permissions, retry or deliberately switch provider config.
- `database_unavailable`: check database readiness and connection string.

`CLEARCV_OCR_LANGUAGE=eng+fra` requires `tesseract-ocr-fra` installed in the image/host. Text-based PDFs preserve Unicode; the default scan OCR language is English. Unsupported locales/section headings in offline rules produce omissions requiring review.

## Database schema
The first startup creates the v1 `resume_records` table if absent. This initial release has no destructive migrations. Future releases that change relational columns need explicit migrations; `create_all` is not a schema-upgrade system. The stored payload has `schema_version=1.0`; update readers and migrate payloads deliberately if changing it.

## Reproducibility
`uv.lock`, hash-pinned `requirements.lock`, and `web/package-lock.json` pin application dependencies. Docker base tags follow maintained patch releases; for immutable deployment pin approved image digests in your own release process. GitHub CI exercises PostgreSQL persistence, the Python suite, synthetic evaluation, a production frontend build, browser workflows, and a Docker readiness smoke test.
