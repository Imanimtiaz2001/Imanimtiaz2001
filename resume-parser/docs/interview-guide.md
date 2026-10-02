# Explain ClearCV in an interview

## One-minute walkthrough
I built a PDF resume parser for a recruiting team's data-entry workflow. The API extracts page text and runs OCR on scans, then a provider returns a typed resume contract. Every extracted value includes source line IDs and a verbatim quote. A second deterministic check rejects fabricated evidence. Experience is calculated from the union of job-date intervals, with a range for year-only dates. A React interface shows the fields beside highlighted source text and supports JSON/CSV exports, history and deletion.

## Decisions worth explaining
- **Why schema validation?** It rejects wrong types, unexpected keys and malformed model responses before persistence. It cannot establish truth; evidence checks and human review are separate.
- **Why PostgreSQL?** Records have stable identities, UTC timestamps, retention queries and transactional writes. JSON stores the versioned extraction payload. Relational columns index lookup/expiry. SQLite serves the same repository interface for local development.
- **Why no JWT?** This is a local single-team tool, protected by an optional random operator key. JWT adds token issuance and rotation without solving record ownership. A multi-tenant deployment would need OIDC and an owner on every record.
- **Why no vector database, RAG or agent framework?** The whole bounded document fits the extraction context. Retrieval could drop evidence. There is one extraction task, not independent agents to coordinate.
- **Why two providers?** Offline rules make the project reproducible without an account. Structured LLM extraction handles varied wording; its failures never silently fall back to a different provider.
- **Why intervals rather than summing durations?** Concurrent contracts and overlapping jobs can inflate tenure. Merge month intervals; show uncertainty for imprecise source dates.
- **Why isolate PDF processing?** PDFs are untrusted binary inputs. A subprocess can be terminated, bounds page rendering, caps text and CPU/memory, and cleans temporary OCR images. It is defense in depth, not a complete operating-system sandbox.
- **How did you evaluate it?** Field exact match, skill precision/recall and grounded evidence on six synthetic formats; property tests compare interval unions with a set oracle; browser tests exercise actual upload/review/export/delete. This is a regression suite, not a representative resume benchmark.
- **What are the failure modes?** OCR errors, unfamiliar layouts, genuine quotes assigned to the wrong field, missing/unusual dates, model refusals, provider outages and database failures. Return null/review notes or explicit errors; never save a partial provider result.

## Honest CV wording
Built ClearCV, an evidence-grounded resume PDF parser using FastAPI, React/TypeScript, Pydantic, PostgreSQL, Tesseract OCR and schema-constrained LLM extraction; implemented source verification, overlap-aware experience calculation, exports, retention and automated regression tests.

Describe this as personal-project experience. Do not call the offline provider an LLM, claim a universal extraction accuracy, or imply cloud/Kubernetes/fine-tuning experience from components not used here.
