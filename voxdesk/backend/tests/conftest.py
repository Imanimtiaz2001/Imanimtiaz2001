import io
import math
import struct
import wave

import httpx
import pytest_asyncio
from voxdesk.config import Settings
from voxdesk.main import create_app
from voxdesk.providers import FixtureProvider


@pytest_asyncio.fixture
async def system(tmp_path):
    provider = FixtureProvider()
    settings = Settings(
        environment="test",
        provider="fixture",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        requests_per_minute=500,
    )
    app = create_app(settings, provider)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            trust_env=False,
            base_url="http://localhost:8000",
            headers={"Origin": "http://localhost:8000"},
        ) as client:
            await client.get("/api/config")
            yield app, client, provider


def wav(seconds=1, silent=False):
    output = io.BytesIO()
    with wave.open(output, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(
            b"".join(
                struct.pack("<h", 0 if silent else int(1200 * math.sin(i * 0.1)))
                for i in range(int(seconds * 16000))
            )
        )
    return output.getvalue()
