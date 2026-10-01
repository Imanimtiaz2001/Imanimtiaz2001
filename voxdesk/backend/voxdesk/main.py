import asyncio
import hashlib
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from starlette.staticfiles import StaticFiles

from .audio import process_audio
from .config import Settings
from .db import BrowserSession, Chunk, Conversation, Database, Document, Turn, now
from .providers import make_provider, provider_error
from .retrieval import chunk_text, valid_vectors
from .schemas import AppError, TurnView
from .security import BodyLimitMiddleware, Limiter, require_origin
from .workflow import PROMPT_VERSION, Workflow

logger = logging.getLogger("voxdesk")
COOKIE = "voxdesk_session"


def turn_view(turn: Turn) -> dict:
    return TurnView(
        id=turn.id,
        request_id=turn.request_id,
        transcript=turn.transcript,
        answer=turn.answer,
        timings=turn.timings,
        audio_url=f"/api/turns/{turn.id}/audio" if turn.audio else None,
        warning=turn.warning,
        mode=turn.mode,
        created_at=turn.created_at.isoformat(),
    ).model_dump()


def create_app(settings: Settings | None = None, provider=None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    ai = provider or make_provider(settings)
    workflow = Workflow(database, ai)
    limiter = Limiter(settings.redis_url, settings.requests_per_minute)
    registry = CollectorRegistry()
    turns_metric = Counter(
        "voxdesk_turns", "Completed assistant turns", ["mode", "status"], registry=registry
    )
    latency = Histogram(
        "voxdesk_stage_seconds", "Pipeline stage latency", ["stage"], registry=registry
    )

    @asynccontextmanager
    async def lifespan(app):
        await database.initialize()
        yield
        await ai.close()
        await limiter.close()
        await database.engine.dispose()

    app = FastAPI(title="VoxDesk API", version="1.0.0", lifespan=lifespan)
    app.state.database, app.state.provider, app.state.workflow = database, ai, workflow
    app.add_middleware(BodyLimitMiddleware, limit=settings.max_audio_bytes + 512 * 1024)

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.trace_id = str(uuid.uuid4())
        start = time.perf_counter()
        try:
            if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
                require_origin(
                    request, settings.public_origin, settings.environment != "production"
                )
            if request.url.path.startswith("/api/"):
                await limiter.check("ip:" + (request.client.host if request.client else "unknown"))
            response = await call_next(request)
        except AppError as exc:
            response = error_response(exc, request)
        response.headers.update(
            {
                "X-Request-ID": request.state.trace_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "Cache-Control": "no-store",
                "Permissions-Policy": "microphone=(self)",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
            }
        )
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        logger.info(
            json.dumps(
                {
                    "trace_id": request.state.trace_id,
                    "method": request.method,
                    "route": request.scope.get("route").path
                    if request.scope.get("route")
                    else "unmatched",
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            )
        )
        return response

    def error_response(exc, request):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
            status_code=exc.status,
            headers={"Retry-After": "60"} if exc.status == 429 else None,
        )

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error_response(exc, request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(
            AppError("invalid_request", "Check the request fields and try again.", 422), request
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error(
            "request_failed trace_id=%s type=%s",
            getattr(request.state, "trace_id", ""),
            type(exc).__name__,
        )
        return error_response(
            AppError("internal_error", "The request failed unexpectedly. Please retry.", 500),
            request,
        )

    async def identity(request: Request) -> str:
        token = request.cookies.get(COOKIE, "")
        if not token or len(token) > 100:
            raise AppError("session_required", "Refresh the app to start a browser session.", 401)
        hashed = hashlib.sha256(token.encode()).hexdigest()
        async with database.sessions() as db:
            session = await db.get(BrowserSession, hashed)
        if session is None:
            raise AppError("session_expired", "Your session expired. Refresh the app.", 401)
        return hashed

    Owner = Annotated[str, Depends(identity)]

    async def owned_conversation(db, identifier, owner):
        row = await db.scalar(
            select(Conversation).where(Conversation.id == identifier, Conversation.owner == owner)
        )
        if row is None:
            raise AppError("not_found", "This conversation was not found.", 404)
        return row

    @app.get("/api/config")
    async def config(request: Request, response: Response):
        token = request.cookies.get(COOKIE, "")
        hashed = hashlib.sha256(token.encode()).hexdigest() if token and len(token) <= 100 else ""
        async with database.sessions() as db:
            if not hashed or await db.get(BrowserSession, hashed) is None:
                token = secrets.token_urlsafe(32)
                db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest()))
                await db.commit()
                response.set_cookie(
                    COOKIE,
                    token,
                    httponly=True,
                    secure=settings.cookie_secure,
                    samesite="lax",
                    max_age=30 * 24 * 3600,
                    path="/",
                )
        return {
            "name": "VoxDesk",
            "provider": settings.provider,
            "ready": await ai.ready(),
            "voices": ["coral", "alloy", "nova"] if settings.provider == "openai" else ["local"],
            "languages": ["auto", "en", "ur"],
            "max_audio_seconds": settings.max_audio_seconds,
            "max_audio_bytes": settings.max_audio_bytes,
            "prompt_version": PROMPT_VERSION,
            "embedding_identity": ai.embedding_identity,
            "setup_hint": "Set OPENAI_API_KEY on the server."
            if settings.provider == "openai"
            else "Run the local setup command to install speech and Ollama models.",
            "voice_disclosure": "Speech is AI-generated.",
        }

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        try:
            await database.ping()
            if limiter.redis:
                await limiter.redis.ping()
            provider_ready = await ai.ready()
            return JSONResponse(
                {"database": "ok", "provider": "configured" if provider_ready else "unavailable"},
                status_code=200 if provider_ready else 503,
            )
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/api/conversations")
    async def list_conversations(owner: Owner):
        async with database.sessions() as db:
            rows = (
                await db.scalars(
                    select(Conversation)
                    .where(Conversation.owner == owner)
                    .order_by(Conversation.created_at.desc())
                    .limit(100)
                )
            ).all()
            return [
                {"id": row.id, "title": row.title, "created_at": row.created_at.isoformat()}
                for row in rows
            ]

    @app.post("/api/conversations", status_code=201)
    async def create_conversation(owner: Owner):
        async with database.sessions() as db:
            if (
                await db.scalar(
                    select(func.count())
                    .select_from(Conversation)
                    .where(Conversation.owner == owner)
                )
                >= 100
            ):
                raise AppError(
                    "conversation_limit", "Delete an old conversation before creating another.", 409
                )
            row = Conversation(owner=owner)
            db.add(row)
            await db.commit()
            return {"id": row.id, "title": row.title, "created_at": row.created_at.isoformat()}

    @app.get("/api/conversations/{identifier}")
    async def get_conversation(identifier: str, owner: Owner):
        async with database.sessions() as db:
            row = await owned_conversation(db, identifier, owner)
            turns = (
                await db.scalars(
                    select(Turn).where(Turn.conversation_id == identifier).order_by(Turn.created_at)
                )
            ).all()
            return {"id": row.id, "title": row.title, "turns": [turn_view(turn) for turn in turns]}

    @app.get("/api/conversations/{identifier}/export")
    async def export_conversation(identifier: str, owner: Owner):
        value = await get_conversation(identifier, owner)
        for turn in value["turns"]:
            turn.pop("audio_url")
        return JSONResponse(
            value,
            headers={"Content-Disposition": f'attachment; filename="voxdesk-{identifier}.json"'},
        )

    @app.delete("/api/conversations/{identifier}", status_code=204)
    async def delete_conversation(identifier: str, owner: Owner):
        async with database.sessions() as db:
            await owned_conversation(db, identifier, owner)
            result = await db.execute(
                delete(Conversation).where(
                    Conversation.id == identifier,
                    or_(Conversation.locked_until.is_(None), Conversation.locked_until < now()),
                )
            )
            if not result.rowcount:
                raise AppError(
                    "conversation_busy",
                    "Wait for the active answer before deleting this conversation.",
                    409,
                )
            await db.commit()
        return Response(status_code=204)

    @app.post("/api/conversations/{identifier}/turns")
    async def create_turn(
        identifier: str,
        owner: Owner,
        request_id: Annotated[str, Form()],
        text: Annotated[str | None, Form()] = None,
        audio: Annotated[UploadFile | None, File()] = None,
        mode: Annotated[str, Form()] = "general",
        language: Annotated[str, Form()] = "auto",
        voice: Annotated[str, Form()] = "coral",
    ):
        try:
            request_id = str(uuid.UUID(request_id))
        except ValueError as exc:
            raise AppError("invalid_request_id", "request_id must be a UUID.", 422) from exc
        if (
            mode not in {"general", "knowledge"}
            or language not in {"auto", "en", "ur"}
            or voice not in {"coral", "alloy", "nova", "local"}
        ):
            raise AppError("invalid_options", "Unsupported mode, language or voice.", 422)
        if bool(audio) == bool(text and text.strip()):
            raise AppError(
                "invalid_input", "Provide either one recording or a non-empty text question.", 422
            )
        raw = await audio.read(settings.max_audio_bytes + 1) if audio else b""
        if audio:
            await audio.close()
        if len(raw) > settings.max_audio_bytes:
            raise AppError("audio_too_large", "Audio files must be 10 MB or smaller.", 413)
        question = (text or "").strip()
        if len(question) > 4000:
            raise AppError("text_too_long", "Questions must be 4,000 characters or shorter.", 413)
        input_hash = hashlib.sha256(
            raw + json.dumps([question, mode, language, voice]).encode()
        ).hexdigest()
        lock_id = str(uuid.uuid4())
        async with database.sessions() as db:
            await owned_conversation(db, identifier, owner)
            existing = await db.scalar(
                select(Turn).where(
                    Turn.conversation_id == identifier, Turn.request_id == request_id
                )
            )
            if existing:
                if existing.input_hash != input_hash:
                    raise AppError(
                        "request_id_reused", "Use a new request ID for a different question.", 409
                    )
                return turn_view(existing)
            if (
                await db.scalar(
                    select(func.count()).select_from(Turn).where(Turn.conversation_id == identifier)
                )
                >= 200
            ):
                raise AppError(
                    "turn_limit", "This conversation is full. Start a new conversation.", 409
                )
            acquired = await db.execute(
                update(Conversation)
                .where(
                    Conversation.id == identifier,
                    or_(Conversation.locked_until.is_(None), Conversation.locked_until < now()),
                )
                .values(
                    locked_until=now() + timedelta(seconds=settings.turn_timeout + 30),
                    locked_by=lock_id,
                )
            )
            if not acquired.rowcount:
                await db.rollback()
                raise AppError(
                    "conversation_busy", "This conversation is already answering a question.", 409
                )
            # A previous request may have committed between the first lookup and lease acquisition.
            replay = await db.scalar(
                select(Turn).where(
                    Turn.conversation_id == identifier, Turn.request_id == request_id
                )
            )
            if replay:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == identifier, Conversation.locked_by == lock_id)
                    .values(locked_until=None, locked_by=None)
                )
                await db.commit()
                if replay.input_hash != input_hash:
                    raise AppError(
                        "request_id_reused", "Use a new request ID for a different question.", 409
                    )
                return turn_view(replay)
            await db.commit()
        start, timings, warning, speech = time.perf_counter(), {}, None, None
        try:
            async with asyncio.timeout(settings.turn_timeout):
                if not await ai.ready():
                    raise AppError(
                        "provider_unconfigured",
                        "The voice provider is not ready. See the setup notice.",
                        503,
                    )
                if audio:
                    stage = time.perf_counter()
                    normalized = await process_audio(raw, settings.max_audio_seconds)
                    question = (await ai.transcribe(normalized, language)).strip()
                    timings["transcription_ms"] = round((time.perf_counter() - stage) * 1000, 2)
                    if not question:
                        raise AppError(
                            "no_speech", "No speech was detected. Please record again.", 422
                        )
                    if len(question) > 4000:
                        raise AppError(
                            "transcript_too_long", "The transcript exceeds the question limit.", 413
                        )
                async with database.sessions() as db:
                    prior = (
                        await db.scalars(
                            select(Turn)
                            .where(Turn.conversation_id == identifier)
                            .order_by(Turn.created_at.desc())
                            .limit(6)
                        )
                    ).all()
                history = [
                    {"question": item.transcript[:600], "answer": item.answer["text"][:800]}
                    for item in reversed(prior)
                ]
                result = await workflow.run(owner, question, history, mode)
                timings.update(result["timings"])
                stage = time.perf_counter()
                try:
                    spoken_language = (
                        "ur"
                        if language == "auto"
                        and any("\u0600" <= ch <= "\u06ff" for ch in result["answer"].text)
                        else language
                    )
                    speech = await ai.speak(
                        result["answer"].text,
                        "coral" if voice == "local" and settings.provider == "openai" else voice,
                        spoken_language,
                    )
                    if not speech:
                        raise AppError("speech_failed", "No speech audio was returned.", 502)
                except Exception as exc:
                    warning = "Your text answer is ready, but speech failed. Use Retry voice to try again."
                    logger.warning("speech_failed type=%s", type(exc).__name__)
                timings["speech_ms"] = round((time.perf_counter() - stage) * 1000, 2)
                timings["total_ms"] = round((time.perf_counter() - start) * 1000, 2)
                async with database.sessions() as db:
                    row = await owned_conversation(db, identifier, owner)
                    if row.locked_by != lock_id:
                        raise AppError(
                            "lease_lost",
                            "The conversation changed during generation. Please retry.",
                            409,
                        )
                    turn = Turn(
                        conversation_id=identifier,
                        request_id=request_id,
                        input_hash=input_hash,
                        transcript=question,
                        answer=result["answer"].model_dump(),
                        timings=timings,
                        audio=speech,
                        warning=warning,
                        mode=mode,
                    )
                    db.add(turn)
                    if row.title == "New conversation":
                        row.title = question[:80]
                    await db.commit()
                    value = turn_view(turn)
                for stage_name, milliseconds in timings.items():
                    latency.labels(stage=stage_name.removesuffix("_ms")).observe(
                        milliseconds / 1000
                    )
                turns_metric.labels(mode=mode, status="speech_warning" if warning else "ok").inc()
                return value
        except Exception as exc:
            turns_metric.labels(mode=mode, status="error").inc()
            raise provider_error(exc) from exc
        finally:
            async with database.sessions() as db:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == identifier, Conversation.locked_by == lock_id)
                    .values(locked_until=None, locked_by=None)
                )
                await db.commit()

    async def owned_turn(db, identifier, owner):
        turn = await db.scalar(
            select(Turn)
            .join(Conversation)
            .where(Turn.id == identifier, Conversation.owner == owner)
        )
        if turn is None:
            raise AppError("not_found", "This answer was not found.", 404)
        return turn

    @app.get("/api/turns/{identifier}/audio")
    async def get_audio(identifier: str, owner: Owner):
        async with database.sessions() as db:
            turn = await owned_turn(db, identifier, owner)
            if not turn.audio:
                raise AppError("audio_not_found", "No speech is available for this answer.", 404)
            return Response(turn.audio, media_type="audio/wav")

    @app.post("/api/turns/{identifier}/speech")
    async def retry_speech(
        identifier: str,
        owner: Owner,
        voice: Annotated[str, Form()] = "coral",
        language: Annotated[str, Form()] = "auto",
    ):
        if voice not in {"coral", "alloy", "nova", "local"} or language not in {"auto", "en", "ur"}:
            raise AppError("invalid_options", "Unsupported voice or language.", 422)
        async with database.sessions() as db:
            turn = await owned_turn(db, identifier, owner)
            if turn.audio:
                return turn_view(turn)
            spoken_language = (
                "ur"
                if language == "auto"
                and any("\u0600" <= ch <= "\u06ff" for ch in turn.answer["text"])
                else language
            )
            try:
                async with asyncio.timeout(settings.provider_timeout):
                    audio = await ai.speak(
                        turn.answer["text"],
                        "coral" if voice == "local" and settings.provider == "openai" else voice,
                        spoken_language,
                    )
            except Exception as exc:
                raise provider_error(exc) from exc
            if not audio:
                raise AppError("speech_failed", "No speech audio was returned. Please retry.", 502)
            # The parent may have been deleted while the provider ran.
            result = await db.execute(
                update(Turn).where(Turn.id == identifier).values(audio=audio, warning=None)
            )
            if not result.rowcount:
                raise AppError("not_found", "This conversation was deleted.", 404)
            await db.commit()
            await db.refresh(turn)
            return turn_view(turn)

    @app.get("/api/documents")
    async def list_documents(owner: Owner):
        async with database.sessions() as db:
            rows = (
                await db.execute(
                    select(Document, func.count(Chunk.id))
                    .outerjoin(Chunk)
                    .where(Document.owner == owner)
                    .group_by(Document.id)
                    .order_by(Document.created_at.desc())
                )
            ).all()
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "chunks": count,
                    "embedding_model": row.embedding_model,
                }
                for row, count in rows
            ]

    @app.post("/api/documents", status_code=201)
    async def upload_document(owner: Owner, file: Annotated[UploadFile, File()]):
        name = Path(file.filename or "").name[:120]
        if Path(name).suffix.lower() not in {".md", ".txt"}:
            await file.close()
            raise AppError("unsupported_document", "Upload a UTF-8 .txt or .md file.", 422)
        raw = await file.read(256 * 1024 + 1)
        await file.close()
        if len(raw) > 256 * 1024:
            raise AppError("document_too_large", "Notes must be 256 KB or smaller.", 413)
        try:
            content = raw.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise AppError(
                "invalid_encoding", "Save this note as UTF-8 before uploading.", 422
            ) from exc
        if not content or "\x00" in content:
            raise AppError("empty_document", "The note must contain readable text.", 422)
        pieces = chunk_text(content)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        async with database.sessions() as db:
            duplicate = await db.scalar(
                select(Document).where(
                    Document.owner == owner, Document.content_hash == content_hash
                )
            )
            if duplicate:
                return {
                    "id": duplicate.id,
                    "name": duplicate.name,
                    "chunks": await db.scalar(
                        select(func.count())
                        .select_from(Chunk)
                        .where(Chunk.document_id == duplicate.id)
                    ),
                    "duplicate": True,
                }
            document_count = await db.scalar(
                select(func.count()).select_from(Document).where(Document.owner == owner)
            )
            chunk_count = await db.scalar(
                select(func.count())
                .select_from(Chunk)
                .join(Document)
                .where(Document.owner == owner)
            )
            if (
                document_count >= settings.max_documents
                or chunk_count + len(pieces) > settings.max_chunks
            ):
                raise AppError(
                    "knowledge_limit",
                    "Your note collection is full. Delete a note before uploading another.",
                    409,
                )
        try:
            async with asyncio.timeout(settings.turn_timeout):
                vectors = []
                for index in range(0, len(pieces), 16):
                    batch = pieces[index : index + 16]
                    vectors.extend(valid_vectors(await ai.embed(batch), len(batch)))
        except Exception as exc:
            raise provider_error(exc) from exc
        async with database.sessions() as db:
            # Serialize the quota recheck across API replicas using the owning session row.
            if database.engine.dialect.name == "postgresql":
                await db.execute(
                    select(BrowserSession)
                    .where(BrowserSession.token_hash == owner)
                    .with_for_update()
                )
            document_count = await db.scalar(
                select(func.count()).select_from(Document).where(Document.owner == owner)
            )
            chunk_count = await db.scalar(
                select(func.count())
                .select_from(Chunk)
                .join(Document)
                .where(Document.owner == owner)
            )
            if (
                document_count >= settings.max_documents
                or chunk_count + len(pieces) > settings.max_chunks
            ):
                raise AppError(
                    "knowledge_limit",
                    "Your note collection is full. Delete a note before uploading another.",
                    409,
                )
            document = Document(
                owner=owner,
                name=name,
                content_hash=content_hash,
                embedding_model=ai.embedding_identity,
            )
            try:
                db.add(document)
                await db.flush()
                db.add_all(
                    [
                        Chunk(document_id=document.id, position=index, text=piece, embedding=vector)
                        for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
                    ]
                )
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                raise AppError(
                    "duplicate_upload",
                    "This note was uploaded in another request. Refresh your notes.",
                    409,
                ) from exc
            return {
                "id": document.id,
                "name": document.name,
                "chunks": len(pieces),
                "duplicate": False,
            }

    @app.delete("/api/documents/{identifier}", status_code=204)
    async def delete_document(identifier: str, owner: Owner):
        async with database.sessions() as db:
            result = await db.execute(
                delete(Document).where(Document.id == identifier, Document.owner == owner)
            )
            if not result.rowcount:
                raise AppError("not_found", "This note was not found.", 404)
            await db.commit()
        return Response(status_code=204)

    if settings.frontend_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=settings.frontend_dir / "assets"), name="assets")

        @app.get("/")
        async def frontend():
            return FileResponse(settings.frontend_dir / "index.html")

    return app


app = create_app()
