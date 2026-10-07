from datetime import date

from clearcv.dates import estimate
from clearcv.local import extract_local
from clearcv.matching import match_resume_to_jd, parse_job_description
from clearcv.schemas import Document, ParseResult, SourceLine


def make_result(*lines: str) -> ParseResult:
    document = Document(
        lines=[
            SourceLine(id=f"p1-l{i}", page=1, text=text, bbox=None, method="text")
            for i, text in enumerate(lines, 1)
        ],
        page_count=1,
        ocr_pages=[],
        warnings=[],
    )
    fields = extract_local(document)
    experience, _ = estimate(fields.employment, date(2026, 10, 7))
    return ParseResult(
        provider="local",
        model=None,
        prompt_version="test",
        fields=fields,
        experience=experience,
        document=document,
        warnings=[],
        timings_ms={},
    )


def test_jd_parser_extracts_skills_and_experience():
    jd = parse_job_description(
        "Senior Backend Engineer\nRequired: Python, FastAPI, PostgreSQL and Docker.\nMinimum 4+ years experience."
    )
    assert jd.minimum_years == 4
    assert {"python", "fastapi", "postgresql", "docker"} <= {
        requirement.value for requirement in jd.requirements
    }


def test_match_report_is_explainable_and_keeps_parse_result_unchanged():
    result = make_result(
        "Avery Morgan",
        "Work Experience",
        "Acme — Backend Engineer Jan 2021–Present",
        "Built Python and FastAPI services backed by PostgreSQL.",
        "Technical Skills",
        "Python, FastAPI, PostgreSQL",
    )
    original = result.model_dump()
    jd = parse_job_description(
        "Backend Engineer\nRequired: Python, FastAPI, PostgreSQL, Docker.\nMinimum 3+ years experience."
    )
    report = match_resume_to_jd(result, jd)

    assert report.overall_score > 0
    assert {"python", "fastapi", "postgresql"} <= {
        item.requirement for item in report.matched
    }
    assert "docker" in {item.requirement for item in report.missing}
    assert report.experience_gap_years == 0
    assert result.model_dump() == original


def test_experience_gap_is_reported():
    result = make_result(
        "Avery Morgan",
        "Experience",
        "Acme — Engineer Jan 2025–Dec 2025",
        "Skills",
        "Python",
    )
    report = match_resume_to_jd(
        result, parse_job_description("Engineer\nPython required.\nMinimum 5 years experience.")
    )
    assert report.experience_gap_years > 0
    assert any(item.kind == "experience" for item in report.missing)
