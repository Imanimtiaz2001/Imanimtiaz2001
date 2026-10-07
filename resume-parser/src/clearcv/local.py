"""Conservative offline extraction with layout/heading tolerant resume heuristics.

The local provider is deliberately evidence-first: it only emits values copied from
source lines.  It accepts many section labels and common resume layouts, but leaves
ambiguous facts unset instead of guessing.
"""

import re
from collections.abc import Iterable

from clearcv.dates import DATE_RANGE
from clearcv.schemas import Document, Education, Employment, Fact, ResumeFields, SourceLine

# Known technologies are detected anywhere in the resume.  The explicit skills
# section additionally supports arbitrary comma/pipe/bullet separated skill names,
# so this list is an accelerator rather than the parser's vocabulary boundary.
SKILLS = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Kotlin",
    "Swift",
    "C",
    "C++",
    "C#",
    "Go",
    "Rust",
    "Ruby",
    "PHP",
    "Scala",
    "R",
    "MATLAB",
    "SQL",
    "HTML",
    "CSS",
    "Sass",
    "FastAPI",
    "Django",
    "Flask",
    "React",
    "React Native",
    "Next.js",
    "Node.js",
    "Express.js",
    "NestJS",
    "Angular",
    "Vue.js",
    "Svelte",
    "Flutter",
    "Spring",
    "Spring Boot",
    ".NET",
    "PostgreSQL",
    "MySQL",
    "MariaDB",
    "SQL Server",
    "Oracle",
    "MongoDB",
    "DynamoDB",
    "Redis",
    "Elasticsearch",
    "OpenSearch",
    "Snowflake",
    "BigQuery",
    "SQLite",
    "Docker",
    "Kubernetes",
    "Helm",
    "AWS",
    "Azure",
    "GCP",
    "Lambda",
    "S3",
    "SNS",
    "SQS",
    "Terraform",
    "Ansible",
    "Jenkins",
    "Git",
    "GitHub Actions",
    "GitLab CI",
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
    "REST API",
    "GraphQL",
    "gRPC",
    "dbt",
    "Spark",
    "Databricks",
    "Airflow",
    "Prisma",
    "Jest",
    "Pytest",
    "Playwright",
    "Cypress",
    "Figma",
    "Power BI",
    "Tableau",
]

SECTION_ALIASES = {
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "relevant experience",
        "employment",
        "employment history",
        "work history",
        "career history",
        "career experience",
        "professional background",
        "professional history",
        "industry experience",
        "internship experience",
        "internships",
        "positions held",
        "work and leadership experience",
        "professional appointments",
        "career summary",
    },
    "education": {
        "education",
        "academic background",
        "academic history",
        "academic qualifications",
        "qualifications",
        "education and training",
        "education and qualifications",
        "studies",
        "training and education",
    },
    "skills": {
        "skills",
        "technical skills",
        "key skills",
        "core skills",
        "professional skills",
        "technical competencies",
        "core competencies",
        "competencies",
        "technologies",
        "tools and technologies",
        "technical proficiencies",
        "technical expertise",
        "areas of expertise",
        "expertise",
        "tech stack",
        "skills and tools",
        "technology stack",
        "programming skills",
    },
    "other": {
        "projects",
        "project experience",
        "personal projects",
        "academic projects",
        "certifications",
        "certificates",
        "licenses",
        "licenses and certifications",
        "awards",
        "honors",
        "achievements",
        "publications",
        "research",
        "research experience",
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "objective",
        "career objective",
        "languages",
        "language skills",
        "interests",
        "volunteering",
        "volunteer experience",
        "extracurricular activities",
        "activities",
        "contact",
        "contact information",
        "references",
        "additional information",
    },
}

DEGREE = re.compile(
    r"\b(?:B\.?Sc\.?|M\.?Sc\.?|B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|BTech|MTech|"
    r"B\.?E\.?|M\.?E\.?|MBA|MPhil|Ph\.?D\.?|Bachelor(?:'s)?|Master(?:'s)?|Doctorate|"
    r"Associate(?:'s)?|Diploma|Certificate)\b",
    re.I,
)
INSTITUTION = re.compile(
    r"\b(?:university|college|institute|school|academy|polytechnic|faculty|campus)\b", re.I
)
ROLE_WORDS = re.compile(
    r"\b(?:engineer|developer|manager|analyst|consultant|intern|scientist|architect|designer|"
    r"specialist|lead|director|officer|coordinator|administrator|researcher|assistant|associate|"
    r"professor|teacher|accountant|nurse|physician|recruiter|strategist|technician|supervisor|"
    r"founder|owner|president|head|executive|devops|sre|qa|tester|programmer|product|marketing|"
    r"sales|finance|operations|software|backend|frontend|full[ -]?stack|data|machine learning|ai)\b",
    re.I,
)
EMPLOYER_WORDS = re.compile(
    r"\b(?:inc\.?|llc|ltd\.?|limited|corp\.?|corporation|company|co\.?|bank|university|"
    r"college|institute|technologies|technology|solutions|systems|labs?|group|pvt\.?|gmbh|plc|"
    r"hospital|agency|foundation|studio|consulting|services|enterprises?)\b",
    re.I,
)
BULLET = re.compile(r"^\s*[•●▪◦*·‣►✓✔➢➤-]\s+")
HEADING_PREFIX = re.compile(r"^\s*(?:(?:\d{1,2}|[ivxlcdm]{1,5})[.)\-:]?\s+)", re.I)
SKILL_LABEL = re.compile(
    r"^(?:skills?|technical skills?|languages?|programming languages?|frameworks?|libraries|"
    r"databases?|cloud|cloud platforms?|tools?|technologies|platforms?|devops|testing|"
    r"data|ai/?ml|machine learning|frontend|backend)\s*:\s*",
    re.I,
)


def fact(value: str, line: SourceLine) -> Fact:
    return Fact(value=value.strip(), quote=line.text[:1200], line_ids=[line.id])


def _heading_text(text: str) -> str:
    text = HEADING_PREFIX.sub("", text)
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[\s_:•|/\\\-–—]+", " ", text)
    return re.sub(r"[^\w+#. ]+", "", text).strip()


def heading(text: str) -> str | None:
    """Classify a short section heading without mistaking resume content for headings."""
    stripped = text.strip()
    if not stripped or len(stripped) > 90 or DATE_RANGE.search(stripped):
        return None

    # Short trailing annotations are common in headings, e.g. "Work Experience (4+ years)".
    stripped = re.sub(r"\s*\([^)]{1,40}\)\s*$", "", stripped).strip()

    # "Languages: Python, Go" and similar labelled content are values, not headings.
    # A bare "Languages" or "Technical Skills:" still falls through as a heading.
    if re.match(r"^[^:]{1,40}:\s*\S", stripped):
        return None

    cleaned = _heading_text(stripped)
    if not cleaned or len(cleaned.split()) > 7:
        return None
    for section, names in SECTION_ALIASES.items():
        if cleaned in names:
            return section

    tokens = set(cleaned.split())
    vocabularies = {
        "experience": {
            "work",
            "professional",
            "relevant",
            "employment",
            "career",
            "industry",
            "internship",
            "internships",
            "experience",
            "history",
            "background",
            "appointments",
            "positions",
            "leadership",
            "summary",
        },
        "education": {
            "education",
            "academic",
            "qualification",
            "qualifications",
            "training",
            "studies",
            "background",
            "history",
        },
        "skills": {
            "skills",
            "skill",
            "technical",
            "key",
            "core",
            "professional",
            "competencies",
            "competency",
            "proficiencies",
            "proficiency",
            "technologies",
            "technology",
            "tools",
            "expertise",
            "stack",
            "programming",
            "platforms",
            "frameworks",
            "libraries",
            "databases",
            "cloud",
        },
        "other": {
            "projects",
            "project",
            "certifications",
            "certification",
            "certificates",
            "certificate",
            "licenses",
            "license",
            "awards",
            "award",
            "honors",
            "honor",
            "achievements",
            "achievement",
            "publications",
            "publication",
            "research",
            "summary",
            "profile",
            "objective",
            "languages",
            "language",
            "interests",
            "interest",
            "volunteering",
            "volunteer",
            "references",
            "reference",
            "activities",
            "activity",
            "contact",
            "information",
            "additional",
            "personal",
            "extracurricular",
        },
    }
    triggers = {
        "experience": {"experience", "employment", "career", "work"},
        "education": {"education", "academic", "qualification", "qualifications", "studies"},
        "skills": {
            "skills",
            "skill",
            "competencies",
            "competency",
            "proficiencies",
            "proficiency",
            "expertise",
            "stack",
        },
        "other": {
            "projects",
            "project",
            "certifications",
            "certification",
            "certificates",
            "certificate",
            "licenses",
            "license",
            "awards",
            "award",
            "honors",
            "honor",
            "achievements",
            "achievement",
            "publications",
            "publication",
            "research",
            "summary",
            "profile",
            "objective",
            "languages",
            "language",
            "interests",
            "interest",
            "volunteering",
            "volunteer",
            "references",
            "reference",
            "activities",
            "activity",
            "contact",
        },
    }
    for section in ("experience", "education", "skills", "other"):
        if tokens <= vocabularies[section] and tokens & triggers[section]:
            return section
    return None


def name_candidate(text: str) -> bool:
    tokens = text.split()
    if not 2 <= len(tokens) <= 5 or len(text) > 80 or heading(text):
        return False
    if any(symbol in text for symbol in "@|:/0123456789"):
        return False
    if any(
        word.casefold().strip(".,")
        in {
            "resume",
            "curriculum",
            "vitae",
            "engineer",
            "developer",
            "manager",
            "analyst",
            "consultant",
            "skills",
            "education",
            "contact",
            "experience",
            "profile",
        }
        for word in tokens
    ):
        return False
    return all(all(c.isalpha() or c in "'-.’" for c in token) for token in tokens)


def _role_score(text: str) -> int:
    return len(ROLE_WORDS.findall(text))


def _employer_score(text: str) -> int:
    return len(EMPLOYER_WORDS.findall(text))


def _clean_header(text: str) -> str:
    return BULLET.sub("", text).strip(" |,;:-–—")


def _header_candidate(line: SourceLine) -> bool:
    text = _clean_header(line.text)
    if not text or len(text) > 220 or heading(text) or DATE_RANGE.fullmatch(text):
        return False
    if BULLET.match(line.text) or text.endswith((".", ";")):
        return False
    # Long prose is an achievement/description, not a role/company header.
    return len(text.split()) <= 18


def _assign_pair(first: str, second: str, line: SourceLine) -> tuple[Fact | None, Fact | None]:
    """Return (role, employer), preferring lexical evidence over positional convention."""
    first, second = _clean_header(first), _clean_header(second)
    if not first or not second:
        return None, fact(first or second, line) if first or second else None
    r1, r2 = _role_score(first), _role_score(second)
    e1, e2 = _employer_score(first), _employer_score(second)
    if r1 > r2 and e2 >= e1:
        return fact(first, line), fact(second, line)
    if r2 > r1 and e1 >= e2:
        return fact(second, line), fact(first, line)
    if e1 > e2 and r2 >= r1:
        return fact(second, line), fact(first, line)
    if e2 > e1 and r1 >= r2:
        return fact(first, line), fact(second, line)
    # "Role | Company" is the most common inline convention.  For genuinely
    # ambiguous two-line headers, callers use lexical scores before assigning.
    return fact(first, line), fact(second, line)


def split_title(line: SourceLine) -> tuple[Fact | None, Fact | None]:
    text = _clean_header(line.text)
    explicit = re.split(r"\s+(?:at|@)\s+", text, maxsplit=1, flags=re.I)
    if len(explicit) == 2 and all(part.strip() for part in explicit):
        return fact(explicit[0], line), fact(explicit[1], line)
    pieces = re.split(r"\s+(?:\||[-–—])\s+", text, maxsplit=1)
    if len(pieces) == 2 and all(piece.strip() for piece in pieces):
        return _assign_pair(pieces[0], pieces[1], line)
    return None, fact(text, line) if text and len(text) <= 300 else None


def _two_line_title(lines: list[SourceLine]) -> tuple[Fact | None, Fact | None]:
    if not lines:
        return None, None
    if len(lines) == 1:
        return split_title(lines[0])
    first, second = lines[-2], lines[-1]
    a, b = _clean_header(first.text), _clean_header(second.text)
    r1, r2, e1, e2 = _role_score(a), _role_score(b), _employer_score(a), _employer_score(b)
    if r1 > r2 or e2 > e1:
        return fact(a, first), fact(b, second)
    if r2 > r1 or e1 > e2:
        return fact(b, second), fact(a, first)
    # Avoid confidently swapping two opaque organization/title strings.
    # Keep the nearest line as role only when it looks role-like; otherwise
    # preserve both as employer/role using the common Company -> Role layout.
    return fact(b, second), fact(a, first)


def _sectioned(lines: list[SourceLine]) -> dict[str, list[SourceLine]]:
    sections: dict[str, list[SourceLine]] = {
        "experience": [],
        "education": [],
        "skills": [],
        "other": [],
    }
    current: str | None = None
    for line in lines:
        detected = heading(line.text)
        if detected:
            current = detected
            continue
        if current:
            sections[current].append(line)
    return sections


def _employment_from_lines(lines: list[SourceLine]) -> list[Employment]:
    dated = [(i, DATE_RANGE.search(line.text)) for i, line in enumerate(lines)]
    dated = [(i, match) for i, match in dated if match]
    jobs: list[Employment] = []
    for pos, (index, match) in enumerate(dated):
        assert match is not None
        line = lines[index]
        before = line.text[: match.start()].strip(" |,;:-–—")
        after = line.text[match.end() :].strip(" |,;:-–—")
        role = employer = None

        inline = " | ".join(part for part in (before, after) if part)
        if inline:
            inline_line = SourceLine(**{**line.model_dump(), "text": inline})
            role, employer = split_title(inline_line)
            for item in (role, employer):
                if item:
                    item.quote = line.text
        else:
            previous_date = dated[pos - 1][0] if pos else -1
            next_date = dated[pos + 1][0] if pos + 1 < len(dated) else len(lines)
            nearby_before = [
                candidate
                for candidate in lines[max(previous_date + 1, index - 3) : index]
                if _header_candidate(candidate)
            ]
            nearby_after = [
                candidate
                for candidate in lines[index + 1 : min(next_date, index + 3)]
                if _header_candidate(candidate)
            ]
            # Dates are frequently right-aligned on the same visual row or placed
            # before the job header. Prefer preceding headers, then following ones.
            candidates = nearby_before[-2:] if nearby_before else nearby_after[:2]
            role, employer = _two_line_title(candidates)

        if role or employer:
            jobs.append(
                Employment(
                    employer=employer,
                    role=role,
                    start=fact(match["start"], line),
                    end=fact(match["end"], line),
                )
            )
    return jobs


def _education_from_lines(lines: list[SourceLine]) -> list[Education]:
    education: list[Education] = []
    for line in lines:
        if len(line.text) > 1200:
            continue
        degree = institution = None
        date_range = DATE_RANGE.search(line.text)
        trailing_range = (
            date_range
            if date_range and not line.text[date_range.end() :].strip(" ,;|()")
            else None
        )
        # A range such as 2020–2024 represents attendance; graduation is its end.
        year = re.search(r"\b(?:19|20)\d{2}\b", line.text)
        graduation = (
            fact(trailing_range["end"], line)
            if trailing_range
            else fact(year[0], line)
            if year
            else None
        )

        # Keep commas inside degree names; pipes/semicolons are stronger field separators.
        parts = re.split(r"\s*[|;]\s*", line.text)
        for part in parts:
            part_range = DATE_RANGE.search(part)
            if part_range and not part[part_range.end() :].strip(" ,()"):
                cleaned = part[: part_range.start()].strip(" ,-–—")
            else:
                cleaned = re.sub(
                    r"\s*\(?\b(?:19|20)\d{2}\b\)?\s*$", "", part
                ).strip(" ,-")
            if not cleaned or len(cleaned) > 300:
                continue
            if DEGREE.search(cleaned):
                degree = fact(cleaned, line)
            elif INSTITUTION.search(cleaned):
                institution = fact(cleaned, line)
        if (
            not degree
            and not institution
            and graduation
            and education
            and education[-1].graduation is None
        ):
            education[-1].graduation = graduation
            continue
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
    return education


def _skill_parts(line: SourceLine) -> Iterable[str]:
    text = BULLET.sub("", line.text).strip()
    text = SKILL_LABEL.sub("", text)
    if not text or len(text) > 500:
        return []
    # A prose sentence under a skills section is not treated as a bag of skills.
    if len(text.split()) > 24 and not re.search(r"[,|;•·]", text):
        return []
    parts = re.split(r"\s*(?:,|;|\||•|·|/\s+(?=[A-Z]))\s*", text)
    result = []
    for part in parts:
        value = part.strip(" .:-–—()[]")
        if (
            value
            and 1 <= len(value.split()) <= 6
            and len(value) <= 80
            and not DATE_RANGE.search(value)
            and not heading(value)
            and not re.search(r"https?://|www\.|@", value, re.I)
        ):
            result.append(value)
    return result


def _extract_skills(lines: list[SourceLine], skill_lines: list[SourceLine]) -> list[Fact]:
    skills: list[Fact] = []
    seen: set[str] = set()

    def add(value: str, line: SourceLine) -> None:
        key = value.casefold().strip()
        if key and key not in seen and len(skills) < 150:
            skills.append(fact(value, line))
            seen.add(key)

    for line in lines:
        if len(line.text) > 1200:
            continue
        for skill in sorted(SKILLS, key=len, reverse=True):
            match = re.search(
                r"(?<!\w)" + re.escape(skill) + r"(?!\w)",
                line.text,
                0 if skill in {"Go", "R", "C"} else re.I,
            )
            if match:
                add(match[0], line)

    for line in skill_lines:
        for value in _skill_parts(line):
            add(value, line)
    return skills


def extract_local(document: Document) -> ResumeFields:
    lines = document.lines
    name = next((fact(line.text, line) for line in lines[:8] if name_candidate(line.text)), None)
    for line in lines[:20]:
        match = re.match(r"^(?:name|candidate)\s*:\s*(.+)$", line.text, re.I)
        if match and len(match[1]) <= 80:
            name = fact(match[1], line)
            break

    sections = _sectioned(lines)
    jobs = _employment_from_lines(sections["experience"])

    # Heading-free/minimal resumes still occur.  Fall back to date ranges only
    # when nearby text looks employment-like; this avoids turning project or
    # education dates into professional experience.
    if not jobs and not sections["experience"]:
        candidates: list[SourceLine] = []
        for i, line in enumerate(lines):
            if not DATE_RANGE.search(line.text):
                continue
            neighborhood = " ".join(
                item.text for item in lines[max(0, i - 2) : min(len(lines), i + 3)]
            )
            if ROLE_WORDS.search(neighborhood) or EMPLOYER_WORDS.search(neighborhood):
                candidates.extend(lines[max(0, i - 2) : min(len(lines), i + 3)])
        # Preserve document order and remove duplicate line ids.
        unique = {line.id: line for line in candidates}
        jobs = _employment_from_lines([line for line in lines if line.id in unique])

    education = _education_from_lines(sections["education"])
    skills = _extract_skills(lines, sections["skills"])
    return ResumeFields(name=name, skills=skills, employment=jobs[:50], education=education[:30])
