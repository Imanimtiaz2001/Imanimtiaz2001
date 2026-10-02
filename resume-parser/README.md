# ClearCV — Evidence-grounded Resume Parser

A complete PDF-to-structured-data application for recruiting teams. Upload a resume, inspect its **name, technical skills, dated experience and education** beside the source text, and export validated JSON or CSV.

![ClearCV review interface](docs/screenshot.png)

**Stack:** Python 3.12 · FastAPI · Pydantic v2 · React 19 / TypeScript · PostgreSQL / SQLAlchemy · pdfplumber / PDFium · Tesseract OCR · OpenAI Responses structured outputs · Prometheus · Docker · GitHub Actions.

## What works
- Text PDFs, scanned pages and two-column layouts; six synthetic examples included.
- Fixed, versioned schema with strict type validation and no unexpected fields.
- Verbatim source evidence on every extracted fact; unsupported values/citations fail closed.
- Employment interval union prevents overlapping jobs from inflating experience. Year-only dates produce a range.
- Review UI, clickable source highlights, JSON view, JSON/CSV downloads, paginated history and permanent live-record deletion.
- Offline extraction with no API key, plus a real schema-constrained OpenAI provider with consent, bounded retries, timeouts and refusal handling.
- Configurable retention, API-key protection, bounded uploads/concurrency, isolated PDF processing and PII-free telemetry.

**Schema validity is not factual accuracy.** Every record requires human review. Offline rules recognize a limited skill vocabulary and conventional section headings; OCR and uncommon layouts can miss or misassign facts. This tool does not rank candidates or make hiring decisions.

## Run with Docker
```bash
cd resume-parser
cp .env.example .env
docker compose up --build
```
Open **http://localhost:8000**. PostgreSQL runs on the private Compose network. Click a synthetic example, then **Extract resume**, click a field to highlight its evidence, and download JSON or CSV.

## Run locally
Install Python 3.12, Node.js 22+, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Tesseract (`sudo apt-get install tesseract-ocr` on Ubuntu, `brew install tesseract` on macOS).
```bash
cd resume-parser
cp .env.example .env
uv sync --frozen --extra dev
cd web
npm ci
npm run build
cd ..
uv run --frozen uvicorn clearcv.main:app --host 127.0.0.1 --port 8000 --no-access-log
```
This uses SQLite by default. To use PostgreSQL outside Docker, set `CLEARCV_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE` in `.env`.

For hot reload, run the backend with `--reload` and `npm run dev` in `web/` in separate terminals. Vite proxies API requests to port 8000.

## Enable LLM extraction
Set `CLEARCV_PROVIDER=openai`, `CLEARCV_OPENAI_API_KEY` and optionally `CLEARCV_OPENAI_MODEL` in `.env`, then restart. The default is `gpt-4.1-mini`; choose a model available to your account that supports structured outputs. The UI requires consent before sending extracted text to OpenAI. Credentials stay server-side. Provider errors never silently switch to offline rules.

## API
Interactive, locally served OpenAPI explorer: **http://localhost:8000/docs** after building the UI. Machine contract: `/openapi.json`. Operator-key deployments expose an **Authorize** control.
```bash
curl -F 'file=@examples/standard.pdf' http://localhost:8000/api/resumes
# In OpenAI mode add ?consent=true. When configured, add -H 'X-API-Key: YOUR_KEY'.
```
See the [design](docs/design.md) for endpoints and data flow, and the [JSON Schema](docs/schema.json) for the complete result contract.

## Tests and evaluation
```bash
uv run --frozen --extra dev pytest
uv run --frozen --extra dev ruff check src tests scripts
uv run --frozen --extra dev ruff format --check src tests scripts
uv run --frozen python scripts/evaluate.py
cd web
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```
The PostgreSQL integration test runs when `CLEARCV_TEST_POSTGRES_URL` points to an isolated test database. CI provides one. The browser suite starts its own backend and uses a separate SQLite test DB. Synthetic evaluation can also run the configured model: `uv run python scripts/evaluate.py --provider openai --output docs/evaluation-openai.json` (incurs provider charges).

Read [verification](docs/verification.md), [measured evaluation](docs/evaluation.json), [operations](docs/operations.md), and the [interview guide](docs/interview-guide.md). The interview guide explains the design choices and gives truthful CV wording.

## Project map
```text
src/clearcv/        API, extraction providers, OCR, evidence, dates, persistence
tests/             Unit, property, integration and PostgreSQL tests
web/               React review interface and Playwright workflows
examples/          Synthetic PDFs only
scripts/           Fixture generation, schema export and evaluation
docs/              Architecture, schema, measured results and interview notes
compose.yaml       App + PostgreSQL
../.github/workflows/clearcv.yml  Automated verification
```

## Deployment boundary
This release is a local, single-team application, not a multi-tenant hosted ATS. Use an operator key and HTTPS before sharing, and add per-user ownership/OIDC before exposing different teams' records. No real resumes or credentials are included. See the operations guide for exact retention/deletion behavior and provider data handling.

## License
MIT. Third-party dependencies retain their own licenses.
