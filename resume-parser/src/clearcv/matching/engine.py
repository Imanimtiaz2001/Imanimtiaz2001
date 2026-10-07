import re

from clearcv.matching.jd_parser import SKILL_ALIASES
from clearcv.matching.schemas import (
    JobDescription,
    MatchBreakdown,
    MatchReport,
    RequirementMatch,
)
from clearcv.schemas import ParseResult


def _contains(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, re.I))


def _resume_evidence(result: ParseResult) -> list[tuple[str, str]]:
    evidence: list[tuple[str, str]] = []
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
    # Source lines let matching recognize technologies mentioned in project/responsibility text
    # without changing or weakening the stable resume parser.
    evidence.extend((line.text, line.text) for line in result.document.lines)
    return evidence


def _skill_evidence(skill: str, evidence: list[tuple[str, str]]) -> str | None:
    aliases = SKILL_ALIASES.get(skill, (skill,))
    for value, quote in evidence:
        if any(_contains(value.lower(), alias) for alias in aliases):
            return quote
    return None


def _percent(hit: int, total: int) -> int:
    return round(100 * hit / total) if total else 100


def match_resume_to_jd(result: ParseResult, jd: JobDescription) -> MatchReport:
    evidence = _resume_evidence(result)
    matched: list[RequirementMatch] = []
    missing: list[RequirementMatch] = []

    skill_requirements = [req for req in jd.requirements if req.kind == "skill"]
    for requirement in skill_requirements:
        cv_evidence = _skill_evidence(requirement.value, evidence)
        item = RequirementMatch(
            requirement=requirement.value,
            kind=requirement.kind,
            matched=cv_evidence is not None,
            required=requirement.required,
            jd_evidence=requirement.evidence,
            cv_evidence=cv_evidence,
        )
        (matched if item.matched else missing).append(item)

    detected = result.experience.lower_years
    required = jd.minimum_years
    gap = max(0.0, round((required or 0.0) - detected, 2))
    experience_score = 100 if required is None else min(100, round(100 * detected / required)) if required else 100
    if required is not None:
        exp_req = next(req for req in jd.requirements if req.kind == "experience")
        exp_item = RequirementMatch(
            requirement=exp_req.value,
            kind="experience",
            matched=gap == 0,
            required=True,
            jd_evidence=exp_req.evidence,
            cv_evidence=f"ClearCV detected {detected:g} years of dated experience.",
        )
        (matched if exp_item.matched else missing).append(exp_item)

    required_skills = [req for req in skill_requirements if req.required]
    skills_to_score = required_skills or skill_requirements
    skill_hits = sum(_skill_evidence(req.value, evidence) is not None for req in skills_to_score)
    skill_score = _percent(skill_hits, len(skills_to_score))

    required_items = [item for item in [*matched, *missing] if item.required]
    requirement_score = _percent(sum(item.matched for item in required_items), len(required_items))
    overall = round(0.55 * skill_score + 0.30 * experience_score + 0.15 * requirement_score)

    suggestions = []
    for item in missing:
        if item.kind == "skill":
            suggestions.append(
                f"JD mentions {item.requirement}; add it only if you genuinely have this experience and can support it with evidence."
            )
    if gap:
        suggestions.append(
            f"The JD asks for {required:g} years; ClearCV detected {detected:g}, a {gap:g}-year gap."
        )
    if not suggestions:
        suggestions.append("No major Phase 1 gaps were detected; review the evidence before making a decision.")

    return MatchReport(
        overall_score=overall,
        breakdown=MatchBreakdown(
            skills=skill_score, experience=experience_score, requirements=requirement_score
        ),
        required_experience_years=required,
        detected_experience_years=detected,
        experience_gap_years=gap,
        matched=matched,
        missing=missing,
        suggestions=suggestions[:12],
    )
