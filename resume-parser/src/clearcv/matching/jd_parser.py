import re

from clearcv.matching.schemas import JDRequirement, JobDescription

# Curated aliases are deliberately normalized here, outside the resume parser.
SKILL_ALIASES = {
    "javascript": ("javascript", "js"),
    "typescript": ("typescript",),
    "python": ("python",),
    "java": ("java",),
    "react": ("react", "react.js", "reactjs"),
    "next.js": ("next.js", "nextjs"),
    "node.js": ("node.js", "nodejs"),
    "express": ("express", "express.js"),
    "fastapi": ("fastapi",),
    "django": ("django",),
    "flask": ("flask",),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "mongodb": ("mongodb", "mongo db"),
    "dynamodb": ("dynamodb",),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "gcp": ("gcp", "google cloud"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "terraform": ("terraform",),
    "git": ("git",),
    "rest api": ("rest api", "restful api", "restful services"),
    "graphql": ("graphql",),
    "microservices": ("microservices", "microservice"),
    "ci/cd": ("ci/cd", "continuous integration", "continuous delivery"),
}


def _contains(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, re.I))


def parse_job_description(text: str) -> JobDescription:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        raise ValueError("Job description is empty.")

    lines = [line.strip(" \t•-*") for line in text.splitlines() if line.strip()]
    title = lines[0][:120] if lines else None
    lower = clean.lower()
    required_words = ("required", "must", "minimum", "need", "at least")
    requirements: list[JDRequirement] = []

    for skill, aliases in SKILL_ALIASES.items():
        alias = next((item for item in aliases if _contains(lower, item)), None)
        if not alias:
            continue
        sentence = next(
            (line for line in lines if _contains(line.lower(), alias)),
            clean[:1000],
        )
        required = any(word in sentence.lower() for word in required_words)
        requirements.append(
            JDRequirement(value=skill, kind="skill", required=required, evidence=sentence[:1000])
        )

    years = [
        float(value)
        for value in re.findall(
            r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", lower
        )
    ]
    minimum_years = max(years) if years else None
    if minimum_years is not None:
        evidence = next(
            (line for line in lines if re.search(r"\b(?:years?|yrs?)\b", line, re.I)),
            clean[:1000],
        )
        requirements.append(
            JDRequirement(
                value=f"{minimum_years:g}+ years experience",
                kind="experience",
                required=True,
                evidence=evidence[:1000],
            )
        )

    return JobDescription(title=title, minimum_years=minimum_years, requirements=requirements)
