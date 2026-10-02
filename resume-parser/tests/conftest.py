import pytest
from fastapi.testclient import TestClient

from clearcv.api import create_app
from clearcv.config import Settings
from clearcv.schemas import Document, SourceLine


@pytest.fixture
def document():
    return Document(
        lines=[
            SourceLine(id="p1-l1", page=1, text="Maya Chen", bbox=None, method="text"),
            SourceLine(id="p1-l2", page=1, text="Python and JavaScript", bbox=None, method="text"),
        ],
        page_count=1,
        ocr_pages=[],
        warnings=[],
    )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        web_dist=tmp_path / "no-ui",
        _env_file=None,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), raise_server_exceptions=False) as connection:
        yield connection
