# API walkthrough

Interactive schemas are at `/docs`; JSON OpenAPI is at `/openapi.json` when the server is running. All `/api` resources except configuration bootstrap require the HttpOnly browser-session cookie. API clients can use a cookie jar; browsers automatically keep it. Do not put provider keys in API calls from the frontend.

```bash
curl -c cookies.txt http://localhost:8000/api/config
curl -b cookies.txt -X POST http://localhost:8000/api/conversations
```

Copy the returned conversation ID, then submit a text turn. Generate a new UUID for each distinct input; keep the same UUID and options for a retry.

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/conversations/CONVERSATION_ID/turns \
  -F request_id=be3f19f3-6b43-49dc-a2a7-d6c628365abb \
  -F 'text=Why choose PostgreSQL?' -F mode=general -F language=en -F voice=coral
```

For audio, replace `text` with `-F audio=@question.wav`. Never send both. The response includes transcript, structured answer, supporting sources, `audio_url`, stage timings, optional recoverable warning and the request ID. Fetch audio using the same session cookie.

```json
{
  "id": "turn UUID",
  "request_id": "client UUID",
  "transcript": "Why choose PostgreSQL?",
  "answer": {"text": "A concise answer.", "sources": [], "abstained": false},
  "timings": {"retrieval_ms": 0.2, "answer_ms": 700, "speech_ms": 600, "total_ms": 1301},
  "audio_url": "/api/turns/turn-UUID/audio",
  "warning": null,
  "mode": "general",
  "created_at": "ISO timestamp"
}
```

The timing values above are illustrative, not measured benchmarks. Errors have one envelope: `{"error":{"code":"stable_code","message":"actionable message","trace_id":"UUID"}}`. Raw provider exceptions and request content are not returned. 401 means bootstrap/session is missing; 403 means an invalid origin; 404 covers absent or unowned resources; 409 covers overlapping writes, request-ID reuse and quotas; 413 covers upload limits; 422 covers invalid fields/media; 429 covers request budget; 502/503/504 cover invalid/unavailable/timed-out providers.

| Endpoint | Request / response |
|---|---|
| `GET /api/config` | Provider capabilities, readiness, model identity, cookie bootstrap; no secrets |
| `GET /api/conversations` | Owned conversations, newest first, maximum 100 |
| `POST /api/conversations` | Create a conversation |
| `GET /api/conversations/{id}` | Conversation with completed turns |
| `DELETE /api/conversations/{id}` | Delete history and audio; 409 while a turn is active |
| `GET /api/conversations/{id}/export` | Downloadable JSON, excludes audio bytes and URLs |
| `POST /api/conversations/{id}/turns` | Multipart `request_id`, `text` OR `audio`, `mode`, `language`, `voice` |
| `GET /api/turns/{id}/audio` | Owned WAV speech, 404 if missing |
| `POST /api/turns/{id}/speech` | Multipart optional `voice`, `language`; recover missing speech |
| `GET /api/documents` | Owned note metadata and embedding-model identity |
| `POST /api/documents` | Multipart `file` (`.txt` / `.md`); index atomic chunks |
| `DELETE /api/documents/{id}` | Delete note and vector chunks |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database, Redis if configured, provider configuration/dependency readiness |
| `GET /metrics` | Prometheus counters and stage histograms, no user content |

`mode`: `general` or `knowledge`. `language`: `auto`, `en`, `ur`. Cloud voice: `coral`, `alloy`, `nova`; local profile uses `local`. Note duplicates in the same workspace return their existing ID. Documents created with an older embedding model are excluded from retrieval until deleted and re-uploaded. Exported conversations preserve their historical cited excerpts even after their source note is deleted; delete the conversation to remove those historical copies too.
