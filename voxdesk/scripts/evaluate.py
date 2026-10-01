"""Offline retrieval regression or opt-in live answer evaluation; never conflate the two."""

import argparse
import asyncio
import json
import re
import tempfile
import uuid
from pathlib import Path

import httpx
from voxdesk.config import Settings
from voxdesk.main import create_app
from voxdesk.providers import make_provider
from voxdesk.retrieval import retrieve

ROOT = Path(__file__).resolve().parents[1]


def contains_concept(text: str, term: str) -> bool:
    """A small lexical smoke gate, not an entailment judge; tolerate inflections."""

    def normalize(value):
        words = []
        for word in re.findall(r"\w+", value.lower()):
            if len(word) > 4 and word.endswith("s"):
                word = word[:-1]
            for suffix in ("ing", "ed"):
                if len(word) > len(suffix) + 3 and word.endswith(suffix):
                    word = word[: -len(suffix)]
                    break
            words.append(word)
        return " " + " ".join(words) + " "

    return normalize(term) in normalize(text)


async def main(live: bool, output: str):
    cases = json.loads((ROOT / "evals/cases.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings() if live else Settings(environment="test", provider="fixture")
        settings.database_url = f"sqlite+aiosqlite:///{directory}/evaluation.db"
        settings.requests_per_minute = 500
        provider = make_provider(settings)
        app = create_app(settings, provider)
        rows = []
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                trust_env=False,
                base_url="http://localhost:8000",
            ) as client:
                config = await client.get("/api/config")
                if not config.json()["ready"]:
                    raise RuntimeError(
                        "Live provider is not configured. No model evaluation was run."
                    )
                response = await client.post(
                    "/api/documents",
                    files={"file": ("notes.md", (ROOT / "evals/notes.md").read_bytes())},
                )
                response.raise_for_status()
                import hashlib

                owner = hashlib.sha256(client.cookies["voxdesk_session"].encode()).hexdigest()
                for case in cases:
                    sources = await retrieve(app.state.database, provider, owner, case["question"])
                    corpus = " ".join(source.excerpt for source in sources).lower()
                    coverage = all(term.lower() in corpus for term in case["expected_terms"])
                    passed = coverage if case["expect_retrieval"] else not sources
                    row = {"id": case["id"], "retrieved": len(sources), "retrieval_pass": passed}
                    if live:
                        identifier = (await client.post("/api/conversations")).json()["id"]
                        response = await client.post(
                            f"/api/conversations/{identifier}/turns",
                            data={
                                "text": case["question"],
                                "request_id": str(uuid.uuid4()),
                                "mode": "knowledge",
                            },
                        )
                        response.raise_for_status()
                        answer = response.json()["answer"]
                        row.update(
                            {
                                "answer": answer["text"],
                                "abstention_pass": answer["abstained"] == case["expect_abstention"],
                                "answer_terms_pass": all(
                                    contains_concept(answer["text"], term)
                                    for term in case["expected_terms"]
                                )
                                if not case["expect_abstention"]
                                else True,
                                "citations_valid": all(
                                    source["id"] in {value.id for value in sources}
                                    for source in answer["sources"]
                                ),
                            }
                        )
                    rows.append(row)
        report = {
            "kind": "live_model_evaluation"
            if live
            else "offline_lexical_and_fixture_vector_regression",
            "provider": settings.provider,
            "model": settings.chat_model
            if settings.provider == "openai"
            else settings.local_chat_model
            if live
            else "deterministic hash embeddings; not a semantic model benchmark",
            "case_count": len(rows),
            "retrieval_pass_count": sum(row["retrieval_pass"] for row in rows),
            "results": rows,
        }
        if output:
            await asyncio.to_thread(Path(output).write_text, json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        if not all(row["retrieval_pass"] for row in rows):
            raise SystemExit(1)
        if live and not all(
            row["abstention_pass"] and row["citations_valid"] and row["answer_terms_pass"]
            for row in rows
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Calls the configured real provider and may incur charges",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    asyncio.run(main(args.live, args.output))
