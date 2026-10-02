import asyncio
import json

import httpx
import pytest
import respx

from clearcv.config import Settings
from clearcv.provider import ProviderError, extract_openai, strict_schema

ENDPOINT = "https://api.openai.com/v1/responses"
VALID = {
    "name": None,
    "skills": [{"value": "Python", "quote": "Python and JavaScript", "line_ids": ["p1-l2"]}],
    "employment": [],
    "education": [],
}


def output(value=VALID, status="completed"):
    return {
        "status": status,
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}
        ],
    }


def settings():
    return Settings(provider="openai", openai_api_key="test-secret", _env_file=None)


@respx.mock
def test_schema_constrained_request(document):
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=output()))
    fields = asyncio.run(extract_openai(document, settings()))
    assert fields.skills[0].value == "Python"
    body = json.loads(route.calls[0].request.content)
    assert body["store"] is False and body["text"]["format"]["strict"] is True
    assert "p1-l2" in body["input"] and "test-secret" not in json.dumps(body)


@respx.mock
def test_retry_is_bounded(document):
    route = respx.post(ENDPOINT).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=output())]
    )
    asyncio.run(extract_openai(document, settings()))
    assert route.call_count == 2


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(401), "provider_error"),
        (httpx.Response(200, json=output({"garbage": True})), "provider_invalid"),
        (httpx.Response(200, json=output(status="incomplete")), "provider_incomplete"),
        (
            httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "refusal"}]}],
                },
            ),
            "provider_refusal",
        ),
        (httpx.Response(200, json={"status": "completed", "output": []}), "provider_invalid"),
        (httpx.Response(200, content="not json"), "provider_invalid"),
    ],
)
@respx.mock
def test_provider_fails_closed(document, response, code):
    respx.post(ENDPOINT).mock(return_value=response)
    with pytest.raises(ProviderError) as exc:
        asyncio.run(extract_openai(document, settings()))
    assert exc.value.code == code


@respx.mock
def test_network_timeout(document):
    route = respx.post(ENDPOINT).mock(side_effect=httpx.ReadTimeout("timeout"))
    with pytest.raises(ProviderError):
        asyncio.run(extract_openai(document, settings()))
    assert route.call_count == 2


def test_schema_requires_every_property():
    schema = strict_schema()
    for obj in [schema, *schema["$defs"].values()]:
        if obj.get("type") == "object":
            assert (
                set(obj["required"]) == set(obj["properties"])
                and obj["additionalProperties"] is False
            )
