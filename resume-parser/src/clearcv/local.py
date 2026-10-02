"""Conservative no-key baseline. Unknown facts stay null."""

import re

from clearcv.dates import DATE_RANGE
from clearcv.schemas import Document, Education, Employment, Fact, ResumeFields, SourceLine

SKILLS = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "C++",
    "C#",
    "Go",
    "Rust",
    "SQL",
    "HTML",
    "CSS",
    "FastAPI",
    "Django",
    "Flask",
    "React",
    "Next.js",
    "Node.js",
    "Angular",
    "Flutter",
    "Spring Boot",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "Git",
    "GitHub Actions",
    "Terraform",
    "Linux",
    "PyTorch",
    "TensorFlow",
    "Keras",
    "scikit-learn",
    "Pandas",
    "NumPy",
    "Hugging Face",
    "LangChain",
    "LangGraph",
    "LlamaIndex",
    "RAG",
    "Pinecone",
    "OpenAI",
    "MLflow",
    "Celery",
    "Kafka",
    "RabbitMQ",
    "NLP",
    "REST",
    "GraphQL",
    "dbt",
    "Spark",
]
SECTIONS = {
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "career history",
    },
    "education": {"education", "academic background", "qualifications"},
    "skills": {"skills", "technical skills", "technologies", "core competencies"},
    "other": {
        "projects",
        "personal projects",
        "certifications",
        "awards",
        "summary",
        "profile",
        "languages",
        "interests",
        "contact",
    },
}
DEGREE = re.compile(
    r"\b(?:B\.?Sc\.?|M\.?Sc\.?|BS|MS|BA|MA|BTech|MTech|MBA|Ph\.?D\.?|Bachelor(?:'s)?|Master(?:'s)?|Doctorate|Associate(?:'s)?|Diploma)\b",
    re.I,
)
INSTITUTION = re.compile(r"\b(?:university|college|institute|school|NUST|MIT|UCL|FAST)\b", re.I)


def fact(value: str, line: SourceLine) -> Fact:
    return Fact(value=value.strip(), quote=line.text[:1200], line_ids=[line.id])


def heading(text: str) -> str | None:
    cleaned = text.casefold().strip(" :•|-–—")
    for section, names in SECTIONS.items():
        if cleaned in names:
            return section
    return None


def name_candidate(text: str) -> bool:
    tokens = text.split()
    if not 2 <= len(tokens) <= 5 or len(text) > 80 or heading(text):
        return False
    if any(symbol in text for symbol in "@|:/0123456789"):
        return False
    if any(
        word.casefold()
        in {
            "resume",
            "curriculum",
            "vitae",
            "engineer",
            "developer",
            "manager",
            "skills",
            "education",
            "contact",
            "experience",
        }
        for word in tokens
    ):
        return False
    return all(all(c.isalpha() or c in "'-.’" for c in token) for token in tokens)


def split_title(line: SourceLine) -> tuple[Fact | None, Fact | None]:
    text = line.text
    pieces = re.split(r"\s+(?:\||[-–—]|at|@)\s+", text, maxsplit=1)
    if len(pieces) == 2 and all(piece.strip() for piece in pieces):
        return fact(pieces[0], line), fact(pieces[1], line)
    return None, fact(text, line) if len(text) <= 300 else None


def extract_local(document: Document) -> ResumeFields:
    lines = document.lines
    name = next((fact(line.text, line) for line in lines[:6] if name_candidate(line.text)), None)
    # Explicit Name: label is preferable to a header heuristic.
    for line in lines[:15]:
        match = re.match(r"^name\s*:\s*(.+)$", line.text, re.I)
        if match and len(match[1]) <= 80:
            name = fact(match[1], line)
            break
    skills, seen = [], set()
    for line in lines:
        if len(line.text) > 1200:
            continue
        for skill in SKILLS:
            match = re.search(
                r"(?<!\w)" + re.escape(skill) + r"(?!\w)", line.text, 0 if skill == "Go" else re.I
            )
            if match and skill.casefold() not in seen:
                skills.append(fact(match[0], line))
                seen.add(skill.casefold())
    jobs, education = [], []
    section = None
    section_lines: list[SourceLine] = []
    last_job_date = -1
    for line in lines:
        new_section = heading(line.text)
        if new_section:
            section, section_lines, last_job_date = new_section, [], -1
            continue
        if section == "experience":
            match = DATE_RANGE.search(line.text)
            if match and len(line.text) <= 1200:
                prefix = line.text[: match.start()].strip(" |,;:-–—")
                employer, role = None, None
                if prefix:
                    role, employer = split_title(
                        SourceLine(**{**line.model_dump(), "text": prefix})
                    )
                    # Restore the original quote; source line id is unchanged.
                    for field in [employer, role]:
                        if field:
                            field.quote = line.text
                elif section_lines:
                    candidates = section_lines[last_job_date + 1 :]
                    header = next(
                        (
                            candidate
                            for candidate in reversed(candidates)
                            if len(candidate.text) <= 200
                            and not candidate.text.startswith(("•", "-", "*"))
                        ),
                        None,
                    )
                    if header:
                        role, employer = split_title(header)
                        if role is None and len(candidates) >= 2:
                            # Common two-line header: employer followed by role.
                            previous = candidates[-2]
                            if (
                                previous is not header
                                and len(previous.text) <= 200
                                and not previous.text.startswith(("•", "-", "*"))
                            ):
                                employer, role = (
                                    fact(previous.text, previous),
                                    fact(header.text, header),
                                )
                if role or employer:
                    jobs.append(
                        Employment(
                            employer=employer,
                            role=role,
                            start=fact(match["start"], line),
                            end=fact(match["end"], line),
                        )
                    )
                last_job_date = len(section_lines)
            section_lines.append(line)
        elif section == "education" and len(line.text) <= 1200:
            degree = None
            institution = None
            parts = re.split(r"\s*[|;]\s*", line.text)
            for part in parts:
                part = re.sub(r"\s*\(?\b(?:19|20)\d{2}\b\)?\s*$", "", part).strip(" ,-")
                if not part or len(part) > 300:
                    continue
                if DEGREE.search(part):
                    degree = fact(part, line)
                elif INSTITUTION.search(part):
                    institution = fact(part, line)
            year = re.search(r"\b(?:19|20)\d{2}\b", line.text)
            graduation = fact(year[0], line) if year else None
            if (
                not degree
                and not institution
                and graduation
                and education
                and education[-1].graduation is None
            ):
                education[-1].graduation = graduation
            if degree or institution:
                if education and (
                    (institution and not degree and education[-1].institution is None)
                    or (degree and not institution and education[-1].degree is None)
                ):
                    previous = education[-1]
                    previous.institution = previous.institution or institution
                    previous.degree = previous.degree or degree
                    previous.graduation = previous.graduation or graduation
                else:
                    education.append(
                        Education(institution=institution, degree=degree, graduation=graduation)
                    )
    return ResumeFields(name=name, skills=skills, employment=jobs[:50], education=education[:30])
