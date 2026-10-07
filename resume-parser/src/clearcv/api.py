import asyncio
import csv
import io
import time
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from uuid import UUID

import anyio
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from clearcv.config import Settings
from clearcv.dates import estimate
from clearcv.db import Store
from clearcv.evidence import EvidenceError, verify
from clearcv.local import extract_local
from clearcv.matching import match_resume_to_jd, parse_job_description
from clearcv.matching.schemas import CandidateMatch, MatchReport, RankingReport, RankingRequest
from clearcv.pdf import PDFError, extract_pdf
from clearcv.provider import PROMPT_VERSION, ProviderError, extract_openai
from clearcv.schemas import ParseResult, StoredResume
from clearcv.security import Guard


def safe_csv(value: str) -> str:
    # Spreadsheet formula injection includes leading whitespace/control characters.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.database_url, settings.retention_hours)
    registry = CollectorRegistry()
    requests = Counter("clearcv_parses_total", "Parse outcomes", ["outcome"], registry=registry)
    durations = Histogram("clearcv_parse_seconds", "End-to-end parsing duration", registry=registry)
    slots = asyncio.Semaphore(settings.concurrent_parses)

    async def cleanup():
        while True:
            await asyncio.sleep(60)
            # If DB is temporarily unavailable, readiness exposes it; keep cleanup alive.
            with suppress(Exception):
                await anyio.to_thread.run_sync(store.purge)

    @asynccontextmanager
    async def lifespan(app):
        await anyio.to_thread.run_sync(store.initialize)
        await anyio.to_thread.run_sync(store.purge)
        task = asyncio.create_task(cleanup())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        store.engine.dispose()

    app = FastAPI(
        title="ClearCV", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.store = store
    app.add_middleware(Guard, settings=settings)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "request_error", "message": str(exc.detail)}
        )
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request parameters or upload are invalid.",
                }
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "The request could not be completed. Retry later.",
                }
            },
            status_code=500,
        )

    def openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        if settings.api_key.get_secret_value():
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["OperatorKey"] = {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            }
            for path, operations in schema["paths"].items():
                if path.startswith("/api/"):
                    for operation in operations.values():
                        operation["security"] = [{"OperatorKey": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = openapi

    @app.get("/docs", include_in_schema=False)
    def docs():
        if not (settings.web_dist / "assets" / "swagger-ui-bundle.js").exists():
            return HTMLResponse(
                '<html lang="en"><head><title>ClearCV API</title></head><body><h1>ClearCV API</h1><p>Build the frontend to enable the interactive API explorer.</p><a href="/openapi.json">OpenAPI contract</a></body></html>'
            )
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ClearCV API</title><link rel="stylesheet" href="/assets/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="/assets/swagger-ui-bundle.js"></script><script src="/assets/docs-init.js"></script></body></html>'
        )

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            store.ready()
        except Exception as exc:
            raise HTTPException(
                503, {"code": "database_unavailable", "message": "Database is not ready."}
            ) from exc
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {
            "provider": settings.provider,
            "model": settings.openai_model if settings.provider == "openai" else None,
            "max_upload_bytes": settings.max_upload_bytes,
            "max_pages": settings.max_pages,
            "retention_hours": settings.retention_hours,
            "schema_version": "1.0",
        }

    @app.get("/api/metrics")
    def metrics():
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    @app.post("/api/resumes", response_model=StoredResume, status_code=201)
    async def parse(file: UploadFile, consent: bool = False):
        if settings.provider == "openai" and not consent:
            await file.close()
            raise HTTPException(
                422,
                {
                    "code": "consent_required",
                    "message": "Consent is required to send resume text to OpenAI.",
                },
            )
        try:
            if not file.filename or not file.filename.lower().endswith(".pdf"):
                raise HTTPException(415, {"code": "pdf_required", "message": "Choose a PDF file."})
            data = await file.read(settings.max_upload_bytes + 1)
            if len(data) > settings.max_upload_bytes:
                raise HTTPException(
                    413,
                    {"code": "upload_too_large", "message": "PDF exceeds the upload size limit."},
                )
            if not data:
                raise HTTPException(422, {"code": "empty_upload", "message": "PDF is empty."})
        finally:
            await file.close()
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.1)
        except TimeoutError as exc:
            raise HTTPException(
                429, {"code": "busy", "message": "All parser workers are busy. Retry shortly."}
            ) from exc
        started = time.perf_counter()
        try:
            document = await anyio.to_thread.run_sync(
                lambda: extract_pdf(
                    data,
                    max_pages=settings.max_pages,
                    max_chars=settings.max_chars,
                    language=settings.ocr_language,
                    timeout=settings.pdf_timeout_seconds,
                )
            )
            pdf_ms = (time.perf_counter() - started) * 1000
            extraction_start = time.perf_counter()
            if settings.provider == "openai":
                async with asyncio.timeout(settings.provider_timeout_seconds):
                    fields = await extract_openai(document, settings)
            else:
                fields = extract_local(document)
            verify(fields, document)
            experience, warnings = estimate(fields.employment, datetime.now(UTC).date())
            warnings = [*document.warnings, *warnings]
            if not fields.name:
                warnings.append("Name was not identified; review the source header.")
            if not fields.employment:
                warnings.append(
                    "No employment entries were identified; missing dates or unconventional headers may need manual review."
                )
            if not fields.skills:
                warnings.append("No technical skills were identified.")
            if not fields.education:
                warnings.append("No education entries were identified.")
            if settings.provider == "local":
                warnings.append(
                    "Offline extraction uses evidence-grounded heuristics across common resume layouts. Check omissions and ambiguous field assignments."
                )
            warnings.append(
                "Human review is required. Source support does not prove semantic correctness or the authenticity of a resume."
            )
            result = ParseResult(
                provider=settings.provider,
                model=settings.openai_model if settings.provider == "openai" else None,
                prompt_version=PROMPT_VERSION
                if settings.provider == "openai"
                else "local-rules-1.1",
                fields=fields,
                experience=experience,
                document=document,
                warnings=warnings,
                timings_ms={
                    "pdf": round(pdf_ms, 2),
                    "extraction": round((time.perf_counter() - extraction_start) * 1000, 2),
                    "total": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            record = await anyio.to_thread.run_sync(store.save, result)
            requests.labels("success").inc()
            return record
        except PDFError as exc:
            requests.labels("pdf_error").inc()
            raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
        except ProviderError as exc:
            requests.labels("provider_error").inc()
            raise HTTPException(502, {"code": exc.code, "message": str(exc)}) from exc
        except EvidenceError as exc:
            requests.labels("evidence_error").inc()
            raise HTTPException(
                502,
                {
                    "code": "unsupported_evidence",
                    "message": "Extraction contained unsupported evidence. No result was saved.",
                },
            ) from exc
        except TimeoutError as exc:
            requests.labels("provider_timeout").inc()
            raise HTTPException(
                504,
                {
                    "code": "provider_timeout",
                    "message": "Extraction provider timed out. No result was saved.",
                },
            ) from exc
        finally:
            durations.observe(time.perf_counter() - started)
            slots.release()

    @app.post("/api/matches/{record_id}", response_model=MatchReport)
    def match_job(record_id: UUID, job_description: str):
        """Compare a stored parsed resume with a JD without modifying or re-parsing the CV."""
        if not job_description.strip():
            raise HTTPException(
                422,
                {"code": "empty_job_description", "message": "Job description is required."},
            )
        if len(job_description) > 30000:
            raise HTTPException(
                413,
                {"code": "job_description_too_large", "message": "Job description is too long."},
            )
        record = get_record(record_id)
        return match_resume_to_jd(record.result, parse_job_description(job_description))

    @app.post("/api/rankings", response_model=RankingReport)
    def rank_candidates(payload: RankingRequest):
        """Rank stored resumes against one JD using the same evidence-grounded matcher."""
        jd = parse_job_description(payload.job_description)
        seen = set()
        candidates = []
        for resume_id in payload.resume_ids:
            if resume_id in seen:
                continue
            seen.add(resume_id)
            try:
                parsed_id = UUID(resume_id)
            except ValueError as exc:
                raise HTTPException(
                    422,
                    {"code": "invalid_resume_id", "message": "A resume ID is invalid."},
                ) from exc
            record = get_record(parsed_id)
            report = match_resume_to_jd(record.result, jd)
            candidates.append((record, report))
        candidates.sort(
            key=lambda item: (
                -item[1].overall_score,
                -item[1].breakdown.skills,
                -item[1].breakdown.experience,
                item[0].id,
            )
        )
        return RankingReport(
            job_title=jd.title,
            candidates=[
                CandidateMatch(
                    resume_id=record.id,
                    candidate_name=(
                        record.result.fields.name.value if record.result.fields.name else None
                    ),
                    rank=index,
                    report=report,
                )
                for index, (record, report) in enumerate(candidates, 1)
            ],
        )

    @app.get("/api/resumes")
    def history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        return {"items": store.list(limit, offset), "limit": limit, "offset": offset}

    def get_record(record_id: UUID) -> StoredResume:
        record = store.get(str(record_id))
        if not record:
            raise HTTPException(
                404,
                {"code": "not_found", "message": "Resume was deleted, expired, or does not exist."},
            )
        return record

    @app.get("/api/resumes/{record_id}", response_model=StoredResume)
    def get(record_id: UUID):
        return get_record(record_id)

    @app.delete("/api/resumes/{record_id}", status_code=204)
    def remove(record_id: UUID):
        if not store.remove(str(record_id)):
            raise HTTPException(404, {"code": "not_found", "message": "Resume does not exist."})
        return Response(status_code=204)

    @app.get("/api/resumes/{record_id}/export")
    def export(record_id: UUID, format: str = Query("json", pattern="^(json|csv)$")):
        record = get_record(record_id)
        if format == "json":
            return Response(
                record.model_dump_json(indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="resume-{record.id}.json"'},
            )
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["field", "value", "evidence_line_ids", "source_quote"])
        for key, value in record.result.fields.model_dump().items():

            def emit(path, item):
                if item:
                    writer.writerow(
                        [
                            path,
                            safe_csv(item["value"]),
                            " ".join(item["line_ids"]),
                            safe_csv(item["quote"]),
                        ]
                    )

            if key == "name":
                emit(key, value)
            elif key == "skills":
                for i, item in enumerate(value):
                    emit(f"skills[{i}]", item)
            else:
                for i, item in enumerate(value):
                    for label, field in item.items():
                        emit(f"{key}[{i}].{label}", field)
        writer.writerow(["experience.lower_years", record.result.experience.lower_years, "", ""])
        writer.writerow(["experience.upper_years", record.result.experience.upper_years, "", ""])
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="resume-{record.id}.csv"'},
        )

    @app.get("/api/examples/{case}")
    def example(case: str):
        from clearcv.examples import CASES, make_example

        if case not in CASES:
            raise HTTPException(404, {"code": "not_found", "message": "Example does not exist."})
        return Response(
            make_example(case),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{case}.pdf"'},
        )

    if settings.web_dist.is_dir():
        # Exact UI root and assets: unknown /api paths never fall through to HTML.
        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(settings.web_dist / "index.html")

        assets = settings.web_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
    return app
