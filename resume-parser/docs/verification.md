# Verification evidence

## Executed locally
- **71 Python tests passed**, including real PDF extraction/OCR, sidebar layout, Unicode names, year-only dates, password protection, blank/malformed PDFs, page/text limits, worker deadlines, evidence validation, interval-union property tests, API upload/history/JSON/CSV/delete, retention, restart persistence, request size/auth guards, worker saturation and provider contract/failure tests.
- **4 Chromium browser workflows passed**: upload → evidence → JSON/CSV exports → deletion; sidebar/scanned extraction; invalid-file/mobile flow; self-hosted interactive API docs.
- Production TypeScript/Vite build, Python lint/format checks, and frozen dependency installation passed.
- Desktop and mobile screenshots were visually inspected. No page/console errors were recorded in the captured upload/review/docs flow.
- The production npm dependency audit reported zero known vulnerabilities at verification time; this is a point-in-time check, not a permanent guarantee.

## Synthetic evaluation
All six checked-in PDFs passed exact name, employment and education matching, source-grounding checks and exact expected skills. The measured report is [evaluation.json](evaluation.json). Overlapping roles in the conventional example yield 69 months at the fixed evaluation date 2026-10-02. The year-only example gives 48–69 months.

This tiny synthetic suite is a regression corpus. It does **not** establish general accuracy on real-world resumes, model quality, multilingual OCR quality or recruiter productivity improvements.

## Infrastructure and paid-provider boundaries
The PostgreSQL persistence/restart test, Docker image build and container readiness/UI smoke check passed in [GitHub CI](https://github.com/Imanimtiaz2001/Imanimtiaz2001/actions/runs/36951104145). The local environment did not expose a usable Docker daemon or allow a PostgreSQL process under its user restrictions, so the PostgreSQL test was skipped locally and verified on the CI runner instead. CI also passed the Python suite, synthetic evaluation, TypeScript production build and all four browser workflows. A subsequent hardening change adds a regression test for unexpected-error log redaction.

OpenAI transport, strict schema, bounded retry, refusal, incomplete response, timeout and fabricated evidence rejection were tested with mocked responses. A live OpenAI call was not made because no project API key was provided. The implemented provider can be evaluated with synthetic fixtures using the documented command and the operator's own credentials.

## Important behavior
- Every successful output is structurally validated; every fact must have valid, literal source support.
- Genuine source text can still be assigned to the wrong field. Human review remains mandatory.
- Unusual headings, unavailable OCR language packs, OCR substitutions and day-level precision can affect results. Date calculations are explicitly calendar-month estimates.
- Original upload PDFs are not persisted. Derived source text and results are retained for the configured period; deletion does not erase separately exported files or database backups.
