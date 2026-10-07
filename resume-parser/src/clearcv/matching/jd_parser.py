import re

from clearcv.matching.schemas import JDRequirement, JobDescription

SKILL_ALIASES = {
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "python": ("python",),
    "java": ("java",),
    "c#": ("c#", "c sharp"),
    "c++": ("c++",),
    "react": ("react", "react.js", "reactjs"),
    "next.js": ("next.js", "nextjs"),
    "angular": ("angular",),
    "vue": ("vue", "vue.js", "vuejs"),
    "node.js": ("node.js", "nodejs", "node"),
    "express": ("express", "express.js"),
    "nestjs": ("nestjs", "nest.js"),
    "fastapi": ("fastapi",),
    "django": ("django",),
    "flask": ("flask",),
    "spring": ("spring boot", "spring"),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "sql": ("sql",),
    "mongodb": ("mongodb", "mongo db"),
    "dynamodb": ("dynamodb",),
    "redis": ("redis",),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "gcp": ("gcp", "google cloud", "google cloud platform"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "terraform": ("terraform",),
    "git": ("git",),
    "rest api": ("rest api", "restful api", "restful services", "rest apis"),
    "graphql": ("graphql",),
    "microservices": ("microservices", "microservice"),
    "ci/cd": ("ci/cd", "continuous integration", "continuous delivery", "continuous deployment"),
    "machine learning": ("machine learning", "ml"),
    "llm": ("llm", "large language model", "large language models"),
    "rag": ("rag", "retrieval augmented generation", "retrieval-augmented generation"),
    "langchain": ("langchain",),
    "vector database": ("vector database", "vector db", "vector databases"),
    "oauth": ("oauth", "oauth2"),
    "jwt": ("jwt", "json web token"),
    "agile": ("agile", "scrum"),
    "pytest": ("pytest",),
    "playwright": ("playwright",),
}

RELATED_SKILLS = {
    "aws": {"gcp", "azure"},
    "gcp": {"aws", "azure"},
    "azure": {"aws", "gcp"},
    "react": {"next.js"},
    "next.js": {"react"},
    "node.js": {"express", "nestjs"},
    "express": {"node.js", "nestjs"},
    "nestjs": {"node.js", "express"},
    "postgresql": {"sql", "mysql"},
    "mysql": {"sql", "postgresql"},
    "sql": {"postgresql", "mysql"},
    "kubernetes": {"docker"},
    "docker": {"kubernetes"},
    "rest api": {"graphql"},
    "graphql": {"rest api"},
    "llm": {"rag", "langchain"},
    "rag": {"llm", "langchain", "vector database"},
    "vector database": {"rag"},
}

EDUCATION_TERMS = (
    "bachelor", "master", "phd", "doctorate", "degree", "computer science",
    "software engineering", "information technology", "engineering",
)
RESPONSIBILITY_VERBS = (
    "build", "develop", "design", "implement", "lead", "manage", "architect",
    "maintain", "deploy", "integrate", "optimize", "collaborate", "test",
)


def _contains(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, re.I))


def _required(line: str) -> bool:
    lower = line.lower()
    optional = ("preferred", "nice to have", "bonus", "plus", "desirable")
    if any(word in lower for word in optional):
        return False
    return any(word in lower for word in ("required", "must", "minimum", "need", "at least"))


def parse_job_description(text: str) -> JobDescription:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        raise ValueError("Job description is empty.")
    lines = [line.strip(" \t•-*") for line in text.splitlines() if line.strip()]
    title = lines[0][:120] if lines else None
    lower = clean.lower()
    requirements: list[JDRequirement] = []

    for skill, aliases in SKILL_ALIASES.items():
        alias = next((item for item in aliases if _contains(lower, item)), None)
        if not alias:
            continue
        evidence = next((line for line in lines if _contains(line.lower(), alias)), clean[:1000])
        requirements.append(
            JDRequirement(
                value=skill,
                kind="skill",
                required=_required(evidence),
                evidence=evidence[:1000],
                weight=1.5 if _required(evidence) else 0.75,
            )
        )

    years = [
        float(value)
        for value in re.findall(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", lower)
    ]
    minimum_years = max(years) if years else None
    if minimum_years is not None:
        evidence = next(
            (line for line in lines if re.search(r"\b(?:years?|yrs?)\b", line, re.I)), clean[:1000]
        )
        requirements.append(
            JDRequirement(
                value=f"{minimum_years:g}+ years experience",
                kind="experience",
                required=True,
                evidence=evidence[:1000],
                weight=2,
            )
        )

    for line in lines:
        line_lower = line.lower()
        if any(term in line_lower for term in EDUCATION_TERMS) and (
            _required(line) or "qualification" in line_lower or "education" in line_lower
        ):
            requirements.append(
                JDRequirement(
                    value=line[:180],
                    kind="education",
                    required=_required(line),
                    evidence=line[:1000],
                    weight=1.25,
                )
            )
        elif len(line.split()) >= 5 and any(
            re.search(rf"\b{verb}\w*\b", line_lower) for verb in RESPONSIBILITY_VERBS
        ):
            requirements.append(
                JDRequirement(
                    value=line[:180],
                    kind="responsibility",
                    required=_required(line),
                    evidence=line[:1000],
                    weight=1,
                )
            )

    deduped = {}
    for req in requirements:
        deduped[(req.kind, req.value.lower())] = req
    return JobDescription(
        title=title, minimum_years=minimum_years, requirements=list(deduped.values())[:150]
    )
