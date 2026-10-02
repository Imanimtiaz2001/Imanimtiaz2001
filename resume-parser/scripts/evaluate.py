"""Deterministic, reproducible evaluation on synthetic PDFs. No private resumes."""

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path

from clearcv.config import Settings
from clearcv.dates import estimate
from clearcv.evidence import normalized, verify
from clearcv.examples import CASES, make_example
from clearcv.local import extract_local
from clearcv.pdf import extract_pdf
from clearcv.provider import extract_openai


def evaluate(provider: str = "local") -> dict:
    settings = Settings(provider=provider)
    cases = []
    true_positive = false_positive = false_negative = 0
    for case in CASES:
        started = time.perf_counter()
        document = extract_pdf(make_example(case))
        fields = (
            asyncio.run(extract_openai(document, settings))
            if provider == "openai"
            else extract_local(document)
        )
        verify(fields, document)
        expected_name = (
            "Noor Ali" if case == "sparse" else "Élise Martin" if case == "unicode" else "Maya Chen"
        )
        gold_skills = (
            {"python"}
            if case == "sparse"
            else {"python", "fastapi", "postgresql", "docker", "pytorch"}
        )
        actual_skills = {normalized(fact.value) for fact in fields.skills}
        true_positive += len(actual_skills & gold_skills)
        false_positive += len(actual_skills - gold_skills)
        false_negative += len(gold_skills - actual_skills)
        expected_jobs = (
            []
            if case == "sparse"
            else [
                (
                    "ML Engineer",
                    "Northstar Labs",
                    "2021" if case == "year-only" else "Jan 2021",
                    "2023" if case == "year-only" else "Dec 2023",
                ),
                (
                    "Consultant",
                    "Orbit Systems",
                    "2023" if case == "year-only" else "Jan 2023",
                    "Present",
                ),
            ]
        )
        actual_jobs = [
            tuple(f.value if f else None for f in (item.role, item.employer, item.start, item.end))
            for item in fields.employment
        ]
        expected_education = (
            [] if case == "sparse" else [("BS Computer Science", "Example University", "2020")]
        )
        actual_education = [
            tuple(f.value if f else None for f in (item.degree, item.institution, item.graduation))
            for item in fields.education
        ]
        experience, _ = estimate(fields.employment, date(2026, 10, 2))
        cases.append(
            {
                "case": case,
                "schema_valid": True,
                "evidence_valid": True,
                "name_exact": fields.name is not None and fields.name.value == expected_name,
                "skills_exact": actual_skills == gold_skills,
                "employment_exact": actual_jobs == expected_jobs,
                "education_exact": actual_education == expected_education,
                "experience_months": [experience.lower_months, experience.upper_months],
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
    )
    return {
        "provider": provider,
        "corpus": "six synthetic fixtures; not a general accuracy benchmark",
        "as_of": "2026-10-02",
        "cases": cases,
        "aggregate": {
            "name_exact_match": sum(c["name_exact"] for c in cases) / len(cases),
            "employment_exact_match": sum(c["employment_exact"] for c in cases) / len(cases),
            "education_exact_match": sum(c["education_exact"] for c in cases) / len(cases),
            "skills_precision": precision,
            "skills_recall": recall,
            "skills_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["local", "openai"], default="local")
    parser.add_argument("--output", default="docs/evaluation.json")
    args = parser.parse_args()
    result = evaluate(args.provider)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["aggregate"], indent=2))
    if not all(
        all(
            case[key]
            for key in ["name_exact", "skills_exact", "employment_exact", "education_exact"]
        )
        for case in result["cases"]
    ):
        raise SystemExit("Evaluation found extraction regressions")
