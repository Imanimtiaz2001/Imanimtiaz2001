import json

import httpx
import pytest
from openai import AsyncOpenAI
from voxdesk.config import Settings
from voxdesk.providers import SYSTEM_PROMPT, LocalProvider, OpenAIProvider
from voxdesk.schemas import ModelAnswer


def settings():
    return Settings(provider="openai", openai_api_key="test-key-never-real")


async def test_openai_three_model_wire_contracts_and_embeddings():
    requests = []
    answer = ModelAnswer(answer="A concise answer.", source_ids=[], abstained=False)

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/audio/transcriptions"):
            return httpx.Response(200, json={"text": "Hello world"})
        if request.url.path.endswith("/audio/speech"):
            return httpx.Response(
                200, content=b"RIFF-test-wave", headers={"content-type": "audio/wav"}
            )
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": "text-embedding-3-small",
                    "data": [{"object": "embedding", "index": 0, "embedding": [0.1] * 768}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        if request.url.path.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "id": "resp_test",
                    "object": "response",
                    "created_at": 1,
                    "model": "gpt-4.1-mini",
                    "status": "completed",
                    "output": [
                        {
                            "id": "msg_test",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": answer.model_dump_json(),
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                    "parallel_tool_calls": False,
                    "tool_choice": "auto",
                    "tools": [],
                },
            )
        raise AssertionError(request.url)

    provider = OpenAIProvider(settings())
    await provider.client.close()
    provider.client = AsyncOpenAI(
        api_key="test-key-never-real",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False),
        max_retries=0,
    )
    assert await provider.transcribe(b"RIFF-wave", "en") == "Hello world"
    assert (await provider.generate("Hello", [], [], "general")).answer == "A concise answer."
    assert len((await provider.embed(["note"]))[0]) == 768
    assert await provider.speak("hello", "coral", "en") == b"RIFF-test-wave"
    transcription = requests[0].content
    assert b"gpt-4o-mini-transcribe" in transcription and b'name="language"' in transcription
    response_request = json.loads(requests[1].content)
    assert response_request["store"] is False
    assert response_request["text"]["format"]["type"] == "json_schema"
    assert response_request["text"]["format"]["strict"] is True
    assert response_request["input"][0]["content"] == SYSTEM_PROMPT
    assert json.loads(requests[2].content)["dimensions"] == 768
    assert json.loads(requests[3].content)["model"] == "gpt-4o-mini-tts"
    await provider.close()


async def test_local_chat_and_embedding_wire_contract():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {"answer": "Local answer", "source_ids": [], "abstained": False}
                        )
                    }
                },
            )
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1] * 768]})
        raise AssertionError(request.url)

    provider = LocalProvider(Settings())
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        base_url="http://ollama", transport=httpx.MockTransport(handler), trust_env=False
    )
    assert (await provider.generate("Question", [], [], "general")).answer == "Local answer"
    assert len((await provider.embed(["note"]))[0]) == 768
    assert json.loads(requests[0].content)["stream"] is False
    assert json.loads(requests[0].content)["format"]["type"] == "object"
    await provider.close()


async def test_openai_missing_key_not_ready():
    provider = OpenAIProvider(Settings(provider="openai", openai_api_key=""))
    assert not await provider.ready()
    await provider.close()


async def test_local_stt_consumes_normalized_pcm_without_a_second_media_decoder():
    from types import SimpleNamespace

    import numpy as np
    from conftest import wav

    observed = []

    class Whisper:
        def transcribe(self, samples, **options):
            observed.append((samples, options))
            return iter([SimpleNamespace(text=" hello ")]), None

    provider = LocalProvider(Settings())
    provider.whisper = Whisper()
    assert await provider.transcribe(wav(), "en") == "hello"
    assert isinstance(observed[0][0], np.ndarray)
    assert observed[0][0].dtype == np.float32
    assert len(observed[0][0]) == 16000
    assert observed[0][1]["vad_filter"] is True
    await provider.close()


async def test_cancelled_local_transcription_retains_model_lock():
    import asyncio
    import threading

    started, release = threading.Event(), threading.Event()
    provider = LocalProvider(Settings())

    def slow(*args):
        started.set()
        release.wait(timeout=5)
        return "finished"

    provider._transcribe_sync = slow
    task = asyncio.create_task(provider.transcribe(b"ignored", "en"))
    await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    from voxdesk.schemas import AppError

    with pytest.raises(AppError) as exc:
        await provider.transcribe(b"ignored", "en")
    assert exc.value.code == "speech_busy"
    jobs = list(provider.transcription_jobs)
    release.set()
    await asyncio.gather(*jobs)
    await provider.close()
