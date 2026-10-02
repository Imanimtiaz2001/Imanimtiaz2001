import re
import unicodedata

from clearcv.schemas import Document, Fact, ResumeFields


class EvidenceError(ValueError):
    pass


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def all_facts(fields: ResumeFields):
    if fields.name:
        yield fields.name
    yield from fields.skills
    for item in [*fields.employment, *fields.education]:
        for fact in item.__dict__.values():
            if isinstance(fact, Fact):
                yield fact


def verify(fields: ResumeFields, document: Document) -> None:
    """No fabricated evidence, missing lines or unsupported literal values."""
    lines = {line.id: line for line in document.lines}
    positions = {line.id: i for i, line in enumerate(document.lines)}
    for fact in all_facts(fields):
        if any(key not in lines for key in fact.line_ids):
            raise EvidenceError("An extracted field references a nonexistent source line")
        indices = [positions[key] for key in fact.line_ids]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise EvidenceError("Evidence must reference consecutive lines in reading order")
        source = normalized(" ".join(lines[key].text for key in fact.line_ids))
        quote, value = normalized(fact.quote), normalized(fact.value)
        if quote not in source or value not in quote:
            raise EvidenceError("An extracted field is not supported by its quoted source")
        # Token boundaries avoid a fake skill such as 'Java' grounded in 'JavaScript'.
        if not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", quote):
            raise EvidenceError("An extracted value is only a substring of a different word")
