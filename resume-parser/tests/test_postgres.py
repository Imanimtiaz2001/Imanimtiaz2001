"""Real PostgreSQL integration; CI supplies an isolated test database."""

import os

import pytest
from fastapi.testclient import TestClient

from clearcv.api import create_app
from clearcv.config import Settings
from clearcv.examples import make_example


@pytest.mark.skipif(
    not os.getenv("CLEARCV_TEST_POSTGRES_URL"), reason="PostgreSQL test URL not set"
)
def test_postgres_persistence_across_app_restart(tmp_path):
    settings = Settings(
        database_url=os.environ["CLEARCV_TEST_POSTGRES_URL"],
        web_dist=tmp_path / "none",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/resumes", files={"file": ("standard.pdf", make_example("standard"))}
        )
        assert response.status_code == 201, response.text
        record_id = response.json()["id"]
    with TestClient(create_app(settings)) as client:
        assert (
            client.get(f"/api/resumes/{record_id}").json()["result"]["fields"]["name"]["value"]
            == "Maya Chen"
        )
        assert client.get(f"/api/resumes/{record_id}/export?format=csv").status_code == 200
        assert client.delete(f"/api/resumes/{record_id}").status_code == 204
        assert client.get(f"/api/resumes/{record_id}").status_code == 404
