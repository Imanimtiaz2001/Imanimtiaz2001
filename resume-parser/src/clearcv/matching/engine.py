import re

from clearcv.matching.jd_parser import RELATED_SKILLS, SKILL_ALIASES
from clearcv.matching.schemas import (
    JobDescription,
    MatchBreakdown,
    MatchReport,
    RequirementMatch,
)
from clearcv.schemas import ParseResult

STOP_WORDS = {
    "and", "the", "with", "for", "from", "that", "this", "your", "you", "our",
    "will", "have", "has", "are", "into", "using", "work", "working", "years",
    "experience", "required", "preferred", "responsible", "ability",
}


def _contains(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, re.I))


def _resume_evidence(result: ParseResult) -> list[tuple[str, str]]:
    evidence = []
    for fact in result.fields.skills:
        evidence.append((fact.value, fact.quote))
    for job in result.fields.employment:
        for fact in (job.role, job.employer):
            if fact:
                evidence.append((fact.value, fact.quote))
    for item in result.fields.education:
        for fact in (item.degree, item.institution):
            if fact:
                evidence.append((fact.value, fact.quote))
    evidence.extend((line.text, line.text) for line in result.document.lines)
    return evidence


def _skill_match(skill: str, evidence: list[tuple[str, str]]) -> tuple[str | None, str]:
    aliases = SKILL_ALIASES.get(skill, (skill,))
    for value, quote in evidence:
        if any(_contains(value.lower(), alias) for alias in aliases):
            return quote, "exact"
    for related in RELATED_SKILLS.get(skill, set()):
        aliases = SKILL_ALIASES.get(related, (related,))
        for value, quote in evidence:
            if any(_contains(value.lower(), alias) for alias in aliases):
                return quote, "related"
    return None, "missing"


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9+#./-]{2,}", value.lower())
        if token not in STOP_WORDS
    }


def _text_match(requirement: str, evidence: list[tuple[str, str]]) -> tuple[str | None, float]:
    target = _tokens(requirement)
    if not target:
        return None, 0
    best_quote, best = None, 0.0
    for value, quote in evidence:
        source = _tokens(value)
        score = len(target & source) / len(target)
        if score > best:
            best_quote, best = quote, score
    return (best_quote, best) if best >= 0.35 else (None, best)


def _percent(score: float, total: float) -> int:
    return round(100 * score / total) if total else 100


def match_resume_to_jd(result: ParseResult, jd: JobDescription) -> MatchReport:
    evidence = _resume_evidence(result)
    matched, missing = [], []
    scores = {"skill": [0.0, 0.0], "responsibility": [0.0, 0.0], "education": [0.0, 0.0]}

    for req in jd.requirements:
        if req.kind == "experience":
            continue
        if req.kind == "skill":
            cv_evidence, confidence = _skill_match(req.value, evidence)
            credit = 1.0 if confidence == "exact" else 0.65 if confidence == "related" else 0.0
        else:
            cv_evidence, similarity = _text_match(req.value, evidence)
            confidence = "related" if cv_evidence else "missing"
            credit = min(1.0, similarity / 0.65) if cv_evidence else 0.0
        scores[req.kind][0] += credit * req.weight
        scores[req.kind][1] += req.weight
        explanation = (
            "Direct evidence found in the CV."
            if confidence == "exact"
            else "Related evidence found; human review should confirm equivalence."
            if confidence == "related"
            else "No sufficiently supported CV evidence was found."
        )
        item = RequirementMatch(
            requirement=req.value,
            kind=req.kind,
            matched=cv_evidence is not None,
            required=req.required,
            jd_evidence=req.evidence,
            cv_evidence=cv_evidence,
            confidence=confidence,
            explanation=explanation,
        )
        (matched if item.matched else missing).append(item)

    detected = result.experience.lower_years
    required = jd.minimum_years
    gap = max(0.0, round((required or 0.0) - detected, 2))
    experience_score = (
        100 if required is None else min(100, round(100 * detected / required)) if required else 100
    )
    if required is not None:
        exp_req = next(req for req in jd.requirements if req.kind == "experience")
        item = RequirementMatch(
            requirement=exp_req.value,
            kind="experience",
            matched=gap == 0,
            required=True,
            jd_evidence=exp_req.evidence,
            cv_evidence=f"ClearCV detected {detected:g} years of dated experience.",
            confidence="experience" if gap == 0 else "missing",
            explanation=(
                "Detected dated experience meets the JD minimum."
                if gap == 0
                else f"Detected dated experience is {gap:g} years below the JD minimum."
            ),
        )
        (matched if item.matched else missing).append(item)

    skill_score = _percent(*scores["skill"])
    responsibility_score = _percent(*scores["responsibility"])
    education_score = _percent(*scores["education"])
    required_items = [item for item in [*matched, *missing] if item.required]
    requirement_score = _percent(sum(item.matched for item in required_items), len(required_items))
    available = [
        (skill_score, 0.45, scores["skill"][1] > 0),
        (experience_score, 0.25, required is not None),
        (responsibility_score, 0.15, scores["responsibility"][1] > 0),
        (education_score, 0.10, scores["education"][1] > 0),
        (requirement_score, 0.05, bool(required_items)),
    ]
    weight = sum(item[1] for item in available if item[2])
    overall = round(sum(score * factor for score, factor, used in available if used) / weight) if weight else 100

    strengths = [f"{item.requirement}: {item.explanation}" for item in matched[:8]]
    risks = [
        f"{item.requirement}: {'required' if item.required else 'preferred'} requirement lacks supported evidence."
        for item in missing[:8]
    ]
    suggestions = []
    for item in missing:
        if item.kind == "skill":
            suggestions.append(
                f"If accurate, add evidence of {item.requirement} in a project or role; do not add unsupported keywords."
            )
        elif item.kind == "responsibility":
            suggestions.append(
                f"Show a concrete achievement demonstrating: {item.requirement[:100]}"
            )
        elif item.kind == "education":
            suggestions.append("Make the relevant qualification explicit if the CV already supports it.")
    if gap:
        suggestions.append(
            f"The JD asks for {required:g} years; ClearCV detected {detected:g}, a {gap:g}-year gap."
        )
    if not suggestions:
        suggestions.append("No major supported gaps detected; verify evidence and role context manually.")

    return MatchReport(
        overall_score=overall,
        breakdown=MatchBreakdown(
            skills=skill_score,
            experience=experience_score,
            requirements=requirement_score,
            responsibilities=responsibility_score,
            education=education_score,
        ),
        required_experience_years=required,
        detected_experience_years=detected,
        experience_gap_years=gap,
        matched=matched,
        missing=missing,
        suggestions=suggestions[:15],
        strengths=strengths,
        risks=risks,
        summary=(
            f"{overall}% requirements alignment based on supported CV evidence. "
            f"{len(matched)} requirement(s) matched and {len(missing)} need review."
        ),
    )
