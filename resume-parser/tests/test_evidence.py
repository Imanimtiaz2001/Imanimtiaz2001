import pytest
from pydantic import ValidationError

from clearcv.evidence import EvidenceError, verify
from clearcv.schemas import Fact, ResumeFields


def fields(fact):
    return ResumeFields(name=None, skills=[fact], employment=[], education=[])


def test_genuine_fact(document):
    verify(
        fields(Fact(value="Python", quote="Python and JavaScript", line_ids=["p1-l2"])), document
    )


@pytest.mark.parametrize(
    "value,quote,ids",
    [
        ("Python", "Python", ["p1-l9"]),
        ("Rust", "Python and JavaScript", ["p1-l2"]),
        ("Python", "Python, JavaScript", ["p1-l2"]),
        ("Java", "JavaScript", ["p1-l2"]),
        ("Python", "Python", ["p1-l2", "p1-l1"]),
        ("Python", "Python", ["p1-l2", "p1-l2"]),
    ],
)
def test_fabricated_evidence_rejected(document, value, quote, ids):
    with pytest.raises(EvidenceError):
        verify(fields(Fact(value=value, quote=quote, line_ids=ids)), document)


def test_extra_fields_and_wrong_types_are_rejected():
    for kwargs in [
        dict(value=123, quote="123", line_ids=["p1-l1"]),
        dict(value="Python", quote="Python", line_ids=["p1-l1"], confidence=0.99),
        dict(value=" ", quote="Python", line_ids=["p1-l1"]),
    ]:
        with pytest.raises(ValidationError):
            Fact(**kwargs)
    with pytest.raises(ValidationError):
        ResumeFields(name=None, skills=[], employment=[], education=[], ranking=99)
