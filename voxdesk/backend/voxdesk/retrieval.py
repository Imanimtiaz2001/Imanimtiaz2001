import math
import re
from collections import Counter

from sqlalchemy import select

from .db import Chunk, Document
from .schemas import AppError, Source

STOP_WORDS = set(
    "a an and are as at be by for from how i in is it of on or that the this to was what when where which why with you your".split()
)


def tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"\w+", text.lower()) if word not in STOP_WORDS]


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = text.strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("\n", start + size // 2, end), text.rfind(" ", start + size // 2, end)
            )
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def valid_vectors(values: list[list[float]], expected: int) -> list[list[float]]:
    if len(values) != expected:
        raise AppError(
            "invalid_embeddings",
            "The embedding provider returned the wrong number of vectors.",
            502,
        )
    for vector in values:
        if len(vector) != 768 or any(not math.isfinite(float(value)) for value in vector):
            raise AppError(
                "invalid_embeddings", "The embedding provider returned an invalid vector.", 502
            )
        if sum(float(value) ** 2 for value in vector) == 0:
            raise AppError(
                "invalid_embeddings", "The embedding provider returned an empty vector.", 502
            )
    return values


def cosine(left, right):
    numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(float(a) ** 2 for a in left) * sum(float(b) ** 2 for b in right))
    return numerator / denominator if denominator else 0.0


def lexical_scores(question: str, passages: list[str]) -> list[float]:
    """BM25 with bounded per-browser corpus; no cross-workspace ranking."""
    query = tokens(question)
    corpus = [tokens(passage) for passage in passages]
    average = sum(map(len, corpus)) / len(corpus) if corpus else 1
    frequencies = Counter(token for document in corpus for token in set(document))
    result = []
    for document in corpus:
        counts, score = Counter(document), 0.0
        for token in set(query):
            frequency = counts[token]
            idf = math.log(
                1 + (len(corpus) - frequencies[token] + 0.5) / (frequencies[token] + 0.5)
            )
            score += (
                idf
                * frequency
                * 2.5
                / (frequency + 1.5 * (0.25 + 0.75 * len(document) / (average or 1)))
            )
        result.append(score)
    return result


async def retrieve(database, provider, owner: str, question: str) -> list[Source]:
    async with database.sessions() as db:
        query = (
            select(Chunk, Document)
            .join(Document)
            .where(Document.owner == owner, Document.embedding_model == provider.embedding_identity)
        )
        rows = list((await db.execute(query)).all())
        if not rows:
            return []
        vector = valid_vectors(await provider.embed([question], purpose="query"), 1)[0]
        lexical = lexical_scores(question, [chunk.text for chunk, _ in rows])
        if database.engine.dialect.name == "postgresql":
            semantic_query = (
                select(Chunk.id, Chunk.embedding.cosine_distance(vector).label("distance"))
                .join(Document)
                .where(
                    Document.owner == owner, Document.embedding_model == provider.embedding_identity
                )
                .order_by("distance")
                .limit(24)
            )
            semantic = {
                identifier: 1 - float(distance)
                for identifier, distance in (await db.execute(semantic_query)).all()
            }
        else:
            semantic = {chunk.id: cosine(chunk.embedding, vector) for chunk, _ in rows}
    lexical_rank = sorted(range(len(rows)), key=lambda i: lexical[i], reverse=True)
    semantic_rank = sorted(
        range(len(rows)), key=lambda i: semantic.get(rows[i][0].id, -1), reverse=True
    )
    fused = Counter()
    for ranking, is_semantic in [(lexical_rank, False), (semantic_rank, True)]:
        for rank, index in enumerate(ranking[:24]):
            chunk = rows[index][0]
            if (semantic.get(chunk.id, -1) >= 0.50) if is_semantic else (lexical[index] > 0):
                fused[index] += 1 / (60 + rank + 1)
    return [
        Source(
            id=rows[index][0].id,
            document_id=rows[index][1].id,
            name=rows[index][1].name,
            excerpt=rows[index][0].text,
            score=round(float(score), 6),
        )
        for index, score in fused.most_common(6)
    ]
