import asyncio
import uuid

import httpx
import pytest
from conftest import wav
from sqlalchemy import func, select
from voxdesk.db import Chunk, Turn
from voxdesk.schemas import ModelAnswer

NOTE = b"PostgreSQL provides ACID transactions, foreign key constraints, and pgvector for semantic search. Redis provides shared request rate limits across replicas. VoxDesk deletes microphone audio after transcription."


async def conversation(client):
    response = await client.post("/api/conversations")
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def ask(client, identifier, **kwargs):
    data = {"request_id": str(uuid.uuid4()), "text": "Why choose PostgreSQL?", **kwargs}
    return await client.post(f"/api/conversations/{identifier}/turns", data=data)


async def test_full_text_loop_history_audio_export_delete(system):
    app, client, _ = system
    identifier = await conversation(client)
    response = await ask(client, identifier)
    assert response.status_code == 200, response.text
    turn = response.json()
    assert turn["answer"]["text"] and turn["audio_url"]
    assert turn["timings"]["total_ms"] >= 0
    audio = await client.get(turn["audio_url"])
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    history = (await client.get(f"/api/conversations/{identifier}")).json()
    assert len(history["turns"]) == 1
    export = (await client.get(f"/api/conversations/{identifier}/export")).json()
    assert "audio_url" not in export["turns"][0]
    assert (await client.delete(f"/api/conversations/{identifier}")).status_code == 204
    assert (await client.get(turn["audio_url"])).status_code == 404
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Turn)) == 0


async def test_real_audio_decoder_and_transcription_contract(system):
    _, client, _ = system
    identifier = await conversation(client)
    response = await client.post(
        f"/api/conversations/{identifier}/turns",
        data={"request_id": str(uuid.uuid4())},
        files={"audio": ("hello.wav", wav(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["transcript"] == "Why choose PostgreSQL?"
    assert response.json()["timings"]["transcription_ms"] > 0


@pytest.mark.parametrize(
    "audio,code",
    [
        (b"corrupt", "invalid_audio"),
        (wav(silent=True), "no_speech"),
        (wav(0.1), "no_speech"),
        (wav(61), "audio_too_long"),
        (b"", "empty_audio"),
    ],
    ids=["corrupt", "silent", "short", "long", "empty"],
)
async def test_invalid_media_rejected_and_lease_released(system, audio, code):
    _, client, _ = system
    identifier = await conversation(client)
    response = await client.post(
        f"/api/conversations/{identifier}/turns",
        data={"request_id": str(uuid.uuid4())},
        files={"audio": ("audio.wav", audio, "audio/wav")},
    )
    assert response.status_code in {413, 422}, response.text
    assert response.json()["error"]["code"] == code
    assert (await ask(client, identifier)).status_code == 200


async def test_replay_and_conflicting_request_id(system):
    _, client, _ = system
    identifier = await conversation(client)
    request_id = str(uuid.uuid4())
    first = await ask(client, identifier, request_id=request_id)
    second = await ask(client, identifier, request_id=request_id)
    assert first.json()["id"] == second.json()["id"]
    conflict = await ask(client, identifier, request_id=request_id, text="different")
    assert conflict.status_code == 409
    assert len((await client.get(f"/api/conversations/{identifier}")).json()["turns"]) == 1


async def test_ownership_every_resource(system):
    app, client, _ = system
    identifier = await conversation(client)
    turn = (await ask(client, identifier)).json()
    note = (await client.post("/api/documents", files={"file": ("database.md", NOTE)})).json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        trust_env=False,
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:8000"},
    ) as outsider:
        await outsider.get("/api/config")
        assert (await outsider.get("/api/conversations")).json() == []
        assert (await outsider.get("/api/documents")).json() == []
        for method, path in [
            ("GET", f"/api/conversations/{identifier}"),
            ("DELETE", f"/api/conversations/{identifier}"),
            ("GET", f"/api/conversations/{identifier}/export"),
            ("GET", turn["audio_url"]),
            ("POST", f"/api/turns/{turn['id']}/speech"),
            ("DELETE", f"/api/documents/{note['id']}"),
        ]:
            response = await outsider.request(method, path)
            assert response.status_code == 404, (path, response.text)
        assert (await ask(outsider, identifier)).status_code == 404


async def test_knowledge_hybrid_retrieval_and_delete(system):
    app, client, _ = system
    upload = await client.post("/api/documents", files={"file": ("database.md", NOTE)})
    assert upload.status_code == 201, upload.text
    note = upload.json()
    duplicate = await client.post("/api/documents", files={"file": ("other.md", NOTE)})
    assert duplicate.json()["duplicate"] is True
    assert len((await client.get("/api/documents")).json()) == 1
    identifier = await conversation(client)
    response = await ask(client, identifier, mode="knowledge")
    assert response.status_code == 200, response.text
    assert response.json()["answer"]["sources"][0]["name"] == "database.md"
    assert not response.json()["answer"]["abstained"]
    assert (await client.delete(f"/api/documents/{note['id']}")).status_code == 204
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Chunk)) == 0
    response = await ask(client, identifier, mode="knowledge")
    assert response.json()["answer"]["abstained"]


async def test_knowledge_empty_corpus_skips_model(system):
    _, client, provider = system

    async def forbidden(*args):
        raise AssertionError("No model call needed for empty corpus")

    provider.generate = forbidden
    identifier = await conversation(client)
    response = await ask(client, identifier, mode="knowledge")
    assert response.status_code == 200
    assert response.json()["answer"]["abstained"]


@pytest.mark.parametrize("citation", [[], ["fabricated-id"]])
async def test_invalid_citations_force_abstention(system, citation):
    _, client, provider = system
    await client.post("/api/documents", files={"file": ("database.txt", NOTE)})

    async def bad(*args):
        return ModelAnswer(answer="An unsupported claim.", source_ids=citation, abstained=False)

    provider.generate = bad
    response = await ask(client, await conversation(client), mode="knowledge")
    assert response.json()["answer"]["abstained"] is True
    assert response.json()["answer"]["sources"] == []


async def test_speech_failure_preserves_answer_and_retry_recovers(system):
    _, client, provider = system
    original = provider.speak

    async def broken(*args):
        raise TimeoutError()

    provider.speak = broken
    response = await ask(client, await conversation(client))
    turn = response.json()
    assert response.status_code == 200 and turn["warning"] and turn["audio_url"] is None
    provider.speak = original
    response = await client.post(f"/api/turns/{turn['id']}/speech")
    assert (
        response.status_code == 200
        and response.json()["audio_url"]
        and response.json()["warning"] is None
    )


async def test_provider_timeout_has_no_partial_turn(system):
    _, client, provider = system

    async def broken(*args):
        raise TimeoutError("secret provider details")

    original = provider.generate
    provider.generate = broken
    identifier = await conversation(client)
    response = await ask(client, identifier)
    assert response.status_code == 504
    assert "secret" not in response.text
    assert (await client.get(f"/api/conversations/{identifier}")).json()["turns"] == []
    provider.generate = original
    assert (await ask(client, identifier)).status_code == 200


async def test_overlap_rejected_by_database_lease(system):
    _, client, provider = system
    started, release = asyncio.Event(), asyncio.Event()
    original = provider.generate

    async def slow(*args):
        started.set()
        await release.wait()
        return await original(*args)

    provider.generate = slow
    identifier = await conversation(client)
    first = asyncio.create_task(ask(client, identifier))
    await asyncio.wait_for(started.wait(), 5)
    second = await ask(client, identifier)
    assert second.status_code == 409
    assert (await client.delete(f"/api/conversations/{identifier}")).status_code == 409
    release.set()
    assert (await first).status_code == 200


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"text": ""}, "invalid_input"),
        ({"text": " " * 10}, "invalid_input"),
        ({"text": "x" * 4001}, "text_too_long"),
        ({"mode": "wrong"}, "invalid_options"),
        ({"language": "xx"}, "invalid_options"),
        ({"voice": "unknown"}, "invalid_options"),
        ({"request_id": "invalid"}, "invalid_request_id"),
    ],
)
async def test_input_validation(system, kwargs, code):
    _, client, _ = system
    response = await ask(client, await conversation(client), **kwargs)
    assert response.status_code in {422, 413}
    assert response.json()["error"]["code"] == code


async def test_mixed_text_and_audio_rejected(system):
    _, client, _ = system
    identifier = await conversation(client)
    response = await client.post(
        f"/api/conversations/{identifier}/turns",
        data={"request_id": str(uuid.uuid4()), "text": "hello"},
        files={"audio": ("a.wav", wav())},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "name,content,code",
    [
        ("a.pdf", b"pdf", "unsupported_document"),
        ("a.txt", b"", "empty_document"),
        ("a.md", b"\xff\xfe", "invalid_encoding"),
        ("a.md", b"a\x00b", "empty_document"),
        ("a.md", b"x" * 262145, "document_too_large"),
    ],
)
async def test_document_validation(system, name, content, code):
    _, client, _ = system
    response = await client.post("/api/documents", files={"file": (name, content)})
    assert response.status_code in {422, 413}
    assert response.json()["error"]["code"] == code


async def test_invalid_embeddings_not_committed(system):
    _, client, provider = system

    async def invalid(*args):
        return [[float("nan")] * 768]

    provider.embed = invalid
    response = await client.post("/api/documents", files={"file": ("a.md", NOTE)})
    assert response.status_code == 502
    assert (await client.get("/api/documents")).json() == []


async def test_origin_protection_and_security_headers(system):
    _, client, _ = system
    response = await client.post("/api/conversations", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert "X-Request-ID" in response.headers
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    response = await client.get("/api/config")
    assert response.headers["Cache-Control"] == "no-store"


async def test_chunked_body_limit_before_parsing(system):
    app, client, _ = system

    async def body():
        for _ in range(12):
            yield b"x" * (1024 * 1024)

    response = await client.post(
        "/api/documents", content=body(), headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 413


async def test_missing_session_and_health_metrics(system):
    app, client, _ = system
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), trust_env=False, base_url="http://localhost:8000"
    ) as other:
        assert (await other.get("/api/conversations")).status_code == 401
    assert (await client.get("/health/live")).status_code == 200
    assert (await client.get("/health/ready")).status_code == 200
    await ask(client, await conversation(client))
    metrics = await client.get("/metrics")
    assert "voxdesk_turns_total" in metrics.text
    assert "PostgreSQL" not in metrics.text


async def test_model_switch_excludes_old_vectors_and_exposes_identity(system):
    _, client, provider = system
    await client.post("/api/documents", files={"file": ("database.md", NOTE)})
    provider.embedding_identity = "fixture:new-model:768"
    assert (await client.get("/api/config")).json()["embedding_identity"] == "fixture:new-model:768"
    response = await ask(client, await conversation(client), mode="knowledge")
    assert response.json()["answer"]["abstained"]


async def test_model_abstention_never_speaks_an_unrelated_passage(system):
    _, client, provider = system
    await client.post("/api/documents", files={"file": ("database.md", NOTE)})

    async def abstain(*args):
        return ModelAnswer(
            answer="An unrelated passage that the model copied.", source_ids=[], abstained=True
        )

    provider.generate = abstain
    response = await ask(client, await conversation(client), mode="knowledge")
    assert response.status_code == 200
    assert response.json()["answer"]["abstained"]
    assert "unrelated passage" not in response.json()["answer"]["text"]
