import os
import uuid

import httpx
import pytest
from voxdesk.config import Settings
from voxdesk.main import create_app
from voxdesk.providers import FixtureProvider
from voxdesk.security import Limiter


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"), reason="Needs a real PostgreSQL pgvector service"
)
async def test_native_pgvector_and_transactional_voice_loop():
    app = create_app(
        Settings(
            environment="test", provider="fixture", database_url=os.environ["TEST_POSTGRES_URL"]
        ),
        FixtureProvider(),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            trust_env=False,
            base_url="http://localhost:8000",
        ) as client:
            await client.get("/api/config")
            note = await client.post(
                "/api/documents",
                files={
                    "file": (
                        "database.md",
                        b"PostgreSQL provides ACID transactions. Redis provides shared request rate limits.",
                    )
                },
            )
            assert note.status_code == 201, note.text
            identifier = (await client.post("/api/conversations")).json()["id"]
            response = await client.post(
                f"/api/conversations/{identifier}/turns",
                data={
                    "request_id": str(uuid.uuid4()),
                    "text": "What does PostgreSQL provide?",
                    "mode": "knowledge",
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["answer"]["sources"]
            assert not response.json()["answer"]["abstained"]
            assert (await client.get(response.json()["audio_url"])).content[:4] == b"RIFF"
            assert (await client.delete(f"/api/conversations/{identifier}")).status_code == 204
            assert (await client.delete(f"/api/documents/{note.json()['id']}")).status_code == 204


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Needs a real Redis service")
async def test_redis_limit_shared_across_process_instances():
    key = str(uuid.uuid4())
    first, second = (
        Limiter(os.environ["TEST_REDIS_URL"], 2),
        Limiter(os.environ["TEST_REDIS_URL"], 2),
    )
    try:
        await first.check(key)
        await second.check(key)
        from voxdesk.schemas import AppError

        with pytest.raises(AppError) as exc:
            await first.check(key)
        assert exc.value.status == 429
    finally:
        await first.close()
        await second.close()
