from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Text = Annotated[str, Field(min_length=1, max_length=300)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Fact(StrictModel):
    value: Text
    quote: Annotated[str, Field(min_length=1, max_length=1200)]
    line_ids: Annotated[list[str], Field(min_length=1, max_length=8)]

    @field_validator("value", "quote")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Facts must be nonblank text without NUL characters")
        return value.strip()


class Employment(StrictModel):
    employer: Fact | None
    role: Fact | None
    start: Fact | None
    end: Fact | None


class Education(StrictModel):
    institution: Fact | None
    degree: Fact | None
    graduation: Fact | None


class ResumeFields(StrictModel):
    name: Fact | None
    skills: Annotated[list[Fact], Field(max_length=150)]
    employment: Annotated[list[Employment], Field(max_length=50)]
    education: Annotated[list[Education], Field(max_length=30)]


class SourceLine(StrictModel):
    id: str
    page: int = Field(ge=1)
    text: str
    bbox: list[float] | None
    method: Literal["text", "ocr"]


class Document(StrictModel):
    lines: list[SourceLine]
    page_count: int
    ocr_pages: list[int]
    warnings: list[str]


class ExperienceEstimate(StrictModel):
    lower_months: int = Field(ge=0)
    upper_months: int = Field(ge=0)
    lower_years: float = Field(ge=0)
    upper_years: float = Field(ge=0)
    dated_roles: int
    excluded_roles: int
    as_of: str
    policy: str


class ParseResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provider: Literal["local", "openai"]
    model: str | None
    prompt_version: str
    review_required: Literal[True] = True
    fields: ResumeFields
    experience: ExperienceEstimate
    document: Document
    warnings: list[str]
    timings_ms: dict[str, float]


class StoredResume(StrictModel):
    id: str
    created_at: str
    expires_at: str
    result: ParseResult
