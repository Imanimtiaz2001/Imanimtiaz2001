import math

import pytest
from pydantic import ValidationError
from voxdesk.config import Settings
from voxdesk.retrieval import chunk_text, cosine, lexical_scores, valid_vectors
from voxdesk.schemas import AppError
from voxdesk.security import Limiter


def test_chunker_coverage_boundaries_unicode():
    text = ("A technical paragraph with Urdu اردو.\n" * 200).strip()
    pieces = chunk_text(text)
    assert pieces and all(0 < len(piece) <= 900 for piece in pieces)
    assert pieces[0].startswith("A technical")
    assert pieces[-1].endswith("اردو.")
    assert chunk_text("   ") == []


def test_bm25_relevant_document_ranks_first():
    scores = lexical_scores(
        "PostgreSQL transactions",
        ["Use PostgreSQL ACID transactions.", "The weather is sunny.", "Redis caches values."],
    )
    assert scores[0] > scores[1] == scores[2] == 0
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0


@pytest.mark.parametrize("vectors", [[[0.0] * 768], [[1.0] * 767], [[math.inf] * 768], []])
def test_invalid_vectors(vectors):
    with pytest.raises(AppError):
        valid_vectors(vectors, 1)


def test_production_config_rules():
    with pytest.raises(ValidationError):
        Settings(provider="fixture", environment="development")
    with pytest.raises(ValidationError):
        Settings(environment="production")
    Settings(
        environment="production",
        cookie_secure=True,
        public_origin="https://voice.example",
        database_url="postgresql+asyncpg://postgres:test@localhost/test",
        redis_url="redis://localhost:6379",
    )


async def test_limiter_bound_and_limit():
    limiter = Limiter("", 2)
    await limiter.check("one")
    await limiter.check("one")
    with pytest.raises(AppError) as exc:
        await limiter.check("one")
    assert exc.value.status == 429
    await limiter.check("two")
