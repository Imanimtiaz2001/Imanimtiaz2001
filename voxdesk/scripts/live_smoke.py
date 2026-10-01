"""Run real STT → grounded LLM → TTS with synthetic spoken input, no mocked providers."""

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

import httpx
from voxdesk.config import Settings
from voxdesk.main import create_app
from voxdesk.providers import make_provider

REPORT_PATH = Path(__file__).resolve().parents[1] / "docs/live-smoke.json"


async def main():
    settings = Settings()
    settings.requests_per_minute = 100
    provider = make_provider(settings)
    if not await provider.ready():
        raise RuntimeError("Provider is not ready; live smoke test was not executed.")
    sample = await provider.speak(
        "What happens to microphone recordings?",
        "coral" if settings.provider == "openai" else "local",
        "en",
    )
    with tempfile.TemporaryDirectory() as directory:
        settings.database_url = f"sqlite+aiosqlite:///{directory}/smoke.db"
        app = create_app(settings, provider)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                trust_env=False,
                base_url="http://localhost:8000",
                timeout=600,
            ) as client:
                await client.get("/api/config")
                note = b"Microphone recordings are transient. VoxDesk transcribes them and then discards the original recording. Generated answer audio is stored until the conversation is deleted."
                upload = await client.post("/api/documents", files={"file": ("privacy.md", note)})
                upload.raise_for_status()
                conversation = (await client.post("/api/conversations")).json()["id"]
                response = await client.post(
                    f"/api/conversations/{conversation}/turns",
                    data={
                        "request_id": str(uuid.uuid4()),
                        "mode": "knowledge",
                        "language": "en",
                        "voice": "local" if settings.provider == "local" else "coral",
                    },
                    files={"audio": ("question.wav", sample, "audio/wav")},
                )
                assert response.status_code == 200, response.text
                turn = response.json()
                assert (
                    turn["transcript"] and turn["answer"]["text"] and turn["answer"]["sources"]
                ), turn
                assert not turn["answer"]["abstained"], turn
                audio = await client.get(turn["audio_url"])
                audio.raise_for_status()
                assert audio.content.startswith(b"RIFF") and len(audio.content) > 44
                report = {
                    "kind": "real_local_model_smoke"
                    if settings.provider == "local"
                    else "real_cloud_model_smoke",
                    "input": "synthetic English speech, not a human microphone accuracy benchmark",
                    "stt_model": settings.whisper_model
                    if settings.provider == "local"
                    else settings.stt_model,
                    "chat_model": settings.local_chat_model
                    if settings.provider == "local"
                    else settings.chat_model,
                    "tts_model": "espeak-ng"
                    if settings.provider == "local"
                    else settings.tts_model,
                    "embedding_model": provider.embedding_identity,
                    "transcript": turn["transcript"],
                    "answer": turn["answer"]["text"],
                    "citations": len(turn["answer"]["sources"]),
                    "timings": turn["timings"],
                    "output_audio_bytes": len(audio.content),
                    "passed": True,
                }
                output = REPORT_PATH
                await asyncio.to_thread(output.write_text, json.dumps(report, indent=2))
                print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
