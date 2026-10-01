# Running and operating VoxDesk

## Production configuration

Use the provided Docker Compose stack behind a TLS reverse proxy / private ingress. The default published port is bound to `127.0.0.1`, not all host interfaces. Configure `.env` with:

```dotenv
ENVIRONMENT=production
PUBLIC_ORIGIN=https://voice.your-domain.example
COOKIE_SECURE=true
POSTGRES_PASSWORD=replace-with-a-unique-secret
PROVIDER=openai
OPENAI_API_KEY=your-own-key
```

Secrets shown are placeholders; no real credentials are committed. PostgreSQL and Redis are isolated internal services. The settings validator rejects production with insecure cookies, HTTP origins, SQLite or missing Redis. Set an explicit access policy at your ingress before exposing a paid-provider app; anonymous browser isolation does not establish a person's identity. Configure the proxy with a request body ceiling of 11 MB and a request timeout greater than the configured turn deadline (default 240 seconds, local Compose 300). Keep proxy logging from capturing bodies, cookies or authorization headers. If you use the root `/metrics` endpoint remotely, restrict it to your monitoring network.

The API runs as uid 10001 and Compose enables no-new-privileges. Run only one local transcription worker per API process; native CTranslate2 inference is serialized. The small CPU model can be slow on shared machines. Increase `PROVIDER_TIMEOUT` / `TURN_TIMEOUT` only after measuring. Multiple API replicas share PostgreSQL leases and Redis budgets, but each replica loads its own local speech model and consumes additional RAM.

## Database migrations and backups

Compose starts `migrate` before `api`. A fresh development server also initializes its schema for easy tests, but **existing schemas must be changed through Alembic**. Create a revision after changing SQLAlchemy models and inspect its DDL. Run `alembic check` in CI to detect drift.

```bash
uv run --no-sync alembic upgrade head
uv run --no-sync alembic check
```

For PostgreSQL backups:

```bash
docker compose exec -T postgres pg_dump -U voxdesk -d voxdesk > voxdesk-backup.sql
# Restore to a separately created empty database after inspecting the backup.
docker compose exec -T postgres psql -U voxdesk -d voxdesk_restore < voxdesk-backup.sql
```

Backups contain note text, transcripts and generated voice. Treat them as private data. Test restores periodically and encrypt backup storage. PostgreSQL stores WAV bytes to make turn/audio deletion transactional. For higher-volume workloads, move audio to private object storage with short-lived authorization and an explicit cleanup protocol; this project keeps the bounded workspace simpler.

## Health and observability

`/health/live` checks that the process is responsive. `/health/ready` checks the database, Redis when configured, and provider prerequisites. Cloud readiness confirms that a key is configured; it does not make a paid call or validate quota. Local readiness checks Ollama model availability, eSpeak and faster-whisper installation; first inference can still take time to load the cached speech model.

Logs contain trace ID, method, templated route, HTTP status and elapsed time. They do not contain transcripts, notes, session tokens or raw provider responses. `voxdesk_turns_total{mode,status}` counts completed turns and failures; `voxdesk_stage_seconds{stage}` records transcription, retrieval, answer, speech and total timing. The UI also exposes timings for each turn. Metrics currently describe latency and failures, not billable token costs; provider usage dashboards remain the source of cost accounting.

## Recovery playbook

| Symptom | Check / recovery |
|---|---|
| Setup needed | Cloud key; or local `ollama-init` / `whisper-init` logs, model names and eSpeak installation |
| Microphone denied | Browser permission; HTTPS or localhost; upload a recording as an alternative |
| Silence/no speech | Mic input level, duration, recording device; correct technical terms with Edit question |
| 409 conversation busy | Wait for current turn; leases expire after the turn deadline plus 30 seconds if a worker dies |
| Network lost after sending | Reopen history; retry the identical input and request ID to recover a completed result |
| Text answer but no audio | Retry voice; inspect speech provider readiness |
| No relevant notes | Choose My notes, verify UTF-8 format and active embedding identity; re-upload after changing models |
| 503 shared limiter | Restore Redis; production deliberately fails closed instead of bypassing budgets |
| Provider 429/timeout | Check quota/capacity, wait, retry; cloud SDK retries transient faults up to twice |
| Local transcription busy | Wait for the native inference job; browser cancellation cannot stop a running native thread |

Stop containers without deleting data: `docker compose down`. To remove **all persisted data**, use `docker compose down -v`; do that only when you intend to delete notes/history/models. In local mode use the same `-f compose.yaml -f compose.local.yaml` arguments for lifecycle commands.

## Explicit limits

10 MB/60-second recordings; 4,000-character question/transcript; 1,800-character structured answer; 20 notes and 200 chunks per session; 256 KB per note; six retrieved passages and six truncated historical turns; 100 conversations and 200 saved turns per conversation. Notes are indexed synchronously in bounded batches. Redis limits requests per client IP; a multi-user public service should additionally enforce account-specific spend limits at an authenticated ingress. Raw audio preprocessing protects the pipeline from empty/invalid media but is not a full speech-presence classifier or universal FFmpeg security sandbox.
