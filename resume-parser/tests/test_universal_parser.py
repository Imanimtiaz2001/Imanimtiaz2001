from datetime import date

import pytest

from clearcv.dates import DATE_RANGE, parse_date
from clearcv.local import extract_local, heading
from clearcv.schemas import Document, SourceLine


def document(*texts: str) -> Document:
    return Document(
        lines=[
            SourceLine(id=f"p1-l{i}", page=1, text=text, bbox=None, method="text")
            for i, text in enumerate(texts, 1)
        ],
        page_count=1,
        ocr_pages=[],
        warnings=[],
    )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Professional Background", "experience"),
        ("WORK & LEADERSHIP EXPERIENCE", "experience"),
        ("Career Experience", "experience"),
        ("Academic Qualifications", "education"),
        ("Education & Training", "education"),
        ("Tech Stack", "skills"),
        ("Tools & Technologies", "skills"),
        ("Licenses & Certifications", "other"),
    ],
)
def test_section_aliases(label, expected):
    assert heading(label) == expected


def test_inline_role_company_and_date():
    fields = extract_local(
        document(
            "Avery Morgan",
            "Professional Background",
            "Senior Platform Engineer at Acme Systems | Jan 2021 - Present",
            "Built reliable services.",
        )
    )
    job = fields.employment[0]
    assert job.role.value == "Senior Platform Engineer"
    assert job.employer.value == "Acme Systems"
    assert job.start.value == "Jan 2021"
    assert job.end.value == "Present"


def test_company_role_then_date_on_separate_line():
    fields = extract_local(
        document(
            "Avery Morgan",
            "Career History",
            "Acme Technologies",
            "Backend Developer",
            "03/2020 – 08/2023",
            "Globex Ltd",
            "Engineering Manager",
            "Sep 2023 to Current",
        )
    )
    assert [(j.employer.value, j.role.value) for j in fields.employment] == [
        ("Acme Technologies", "Backend Developer"),
        ("Globex Ltd", "Engineering Manager"),
    ]


def test_date_before_header_is_supported():
    fields = extract_local(
        document(
            "Avery Morgan",
            "Employment History",
            "Jan 2022 - Dec 2024",
            "Example Bank",
            "Data Analyst",
        )
    )
    job = fields.employment[0]
    assert job.employer.value == "Example Bank"
    assert job.role.value == "Data Analyst"


def test_explicit_skills_are_not_limited_to_static_dictionary():
    fields = extract_local(
        document(
            "Avery Morgan",
            "Technical Proficiencies",
            "Languages: Elixir, Zig, Solidity",
            "Tools: Temporal, Pulumi, Argo CD",
        )
    )
    values = {skill.value for skill in fields.skills}
    assert {"Elixir", "Zig", "Solidity", "Temporal", "Pulumi", "Argo CD"} <= values


@pytest.mark.parametrize(
    "text",
    [
        "Jan 2024 - Ongoing",
        "2021 until Today",
        "Mar 2020 through Till Date",
        "2022 thru Current",
    ],
)
def test_extended_date_ranges(text):
    match = DATE_RANGE.search(text)
    assert match is not None
    assert parse_date(match["end"], date(2026, 10, 7)) is not None
