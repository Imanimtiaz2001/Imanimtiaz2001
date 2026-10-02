import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import update
from sqlalchemy.orm import Session

from clearcv.api import create_app, safe_csv
from clearcv.config import Settings
from clearcv.db import Record
from clearcv.examples import make_example
from clearcv.schemas import StoredResume


def upload(client, case="standard", **kwargs):
    return client.post(
        "/api/resumes",
        files={"file": ("resume.pdf", make_example(case), "application/pdf")},
        **kwargs,
    )


def test_full_lifecycle(client):
    assert client.get("/health/ready").status_code == 200
    parsed = upload(client)
    assert parsed.status_code == 201, parsed.text
    result = StoredResume.model_validate(parsed.json())
    assert result.result.fields.name.value == "Maya Chen"
    assert client.get("/api/resumes").json()["items"][0]["id"] == result.id
    assert client.get(f"/api/resumes/{result.id}").status_code == 200
    assert (
        client.get(f"/api/resumes/{result.id}/export").json()["result"]["schema_version"] == "1.0"
    )
    csv = client.get(f"/api/resumes/{result.id}/export?format=csv")
    assert "Maya Chen" in csv.text and "source_quote" in csv.text
    assert client.delete(f"/api/resumes/{result.id}").status_code == 204
    assert client.get(f"/api/resumes/{result.id}").status_code == 404
    assert client.get("/api/resumes").json()["items"] == []


@pytest.mark.parametrize(
    "filename,data,status",
    [("file.txt", b"hi", 415), ("file.pdf", b"", 422), ("file.pdf", b"not pdf", 422)],
)
def test_invalid_uploads(client, filename, data, status):
    response = client.post("/api/resumes", files={"file": (filename, data)})
    assert response.status_code == status and "error" in response.json()
    assert client.get("/api/resumes").json()["items"] == []


def test_auth_before_processing(settings):
    settings.api_key = SecretStr("a-secure-key-with-at-least-24-chars")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/config").status_code == 401
        assert client.post("/api/resumes", content=b"bad").status_code == 401
        assert (
            client.get(
                "/api/config", headers={"X-API-Key": settings.api_key.get_secret_value()}
            ).status_code
            == 200
        )
        assert client.get("/api/config", headers={"X-API-Key": "incorrect"}).status_code == 401


def test_actual_file_size_limit(settings):
    settings.max_upload_bytes = 1024
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/resumes", files={"file": ("large.pdf", b"%PDF-" + b"x" * 2000)}
        )
        assert response.status_code == 413 and client.get("/api/resumes").json()["items"] == []


def test_content_length_and_security_headers(client):
    response = client.post("/api/resumes", content=b"tiny", headers={"Content-Length": "50000000"})
    assert response.status_code == 413
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        response.headers["X-Request-ID"]
        and "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    )


def test_chunked_body_capped(settings):
    from clearcv.security import Guard

    messages = iter(
        [
            {
                "type": "http.request",
                "body": b"x" * (settings.max_upload_bytes + 1048577),
                "more_body": True,
            }
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def app(*args):
        raise AssertionError("Oversized body reached the application")

    scope = {"type": "http", "method": "POST", "path": "/api/resumes", "headers": []}
    asyncio.run(Guard(app, settings)(scope, receive, send))
    assert sent[0]["status"] == 413


def test_retention_hides_and_purges(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        record_id = upload(client).json()["id"]
        with Session(app.state.store.engine) as session, session.begin():
            session.execute(
                update(Record)
                .where(Record.id == record_id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert client.get(f"/api/resumes/{record_id}").status_code == 404
        assert client.get("/api/resumes").json()["items"] == []
        app.state.store.purge()
        with Session(app.state.store.engine) as session:
            assert session.get(Record, record_id) is None


@pytest.mark.parametrize("value", ["=HYPERLINK('x')", " +SUM(1)", "-2+3", "@command", "\t=1"])
def test_csv_injection(value):
    assert safe_csv(value).startswith("'")


def test_examples_and_bad_parameters(client):
    assert client.get("/api/examples/standard").content.startswith(b"%PDF-")
    assert client.get("/api/examples/missing").status_code == 404
    assert client.get("/api/resumes?limit=101").status_code == 422
    assert client.get("/api/resumes/not-a-uuid").status_code == 422
    assert client.get("/api/metrics").status_code == 200


def test_missing_provider_key_rejected():
    with pytest.raises(ValueError):
        Settings(provider="openai", openai_api_key="", _env_file=None)


def test_restart_persistence(settings):
    with TestClient(create_app(settings)) as client:
        record_id = upload(client).json()["id"]
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/resumes/{record_id}").status_code == 200


def test_busy_workers_return_429(settings, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import clearcv.api as api
    from clearcv.pdf import extract_pdf

    settings.concurrent_parses = 1
    entered = threading.Event()

    def slow_pdf(*args, **kwargs):
        entered.set()
        time.sleep(0.3)
        return extract_pdf(*args, **kwargs)

    monkeypatch.setattr(api, "extract_pdf", slow_pdf)
    with TestClient(create_app(settings)) as client, ThreadPoolExecutor() as pool:
        first = pool.submit(upload, client)
        assert entered.wait(timeout=5)
        second = upload(client)
        assert second.status_code == 429
        assert first.result(timeout=10).status_code == 201


def test_provider_consent_and_unsupported_facts(settings, monkeypatch):
    import clearcv.api as api
    from clearcv.schemas import Fact, ResumeFields

    settings.provider = "openai"
    settings.openai_api_key = SecretStr("synthetic-only")

    async def fake_provider(*args, **kwargs):
        return ResumeFields(
            name=Fact(value="Invented Name", quote="Invented Name", line_ids=["p1-l1"]),
            skills=[],
            employment=[],
            education=[],
        )

    monkeypatch.setattr(api, "extract_openai", fake_provider)
    with TestClient(create_app(settings)) as client:
        assert upload(client).json()["error"]["code"] == "consent_required"
        response = upload(client, params={"consent": "true"})
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "unsupported_evidence"
        assert client.get("/api/resumes").json()["items"] == []
