from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JDRequirement(MatchModel):
    value: str = Field(min_length=1, max_length=120)
    kind: Literal["skill", "experience", "education", "responsibility"]
    required: bool = True
    evidence: str = Field(min_length=1, max_length=1000)


class JobDescription(MatchModel):
    title: str | None = None
    minimum_years: float | None = Field(default=None, ge=0, le=50)
    requirements: list[JDRequirement] = Field(default_factory=list, max_length=150)


class RequirementMatch(MatchModel):
    requirement: str
    kind: str
    matched: bool
    required: bool
    jd_evidence: str
    cv_evidence: str | None = None


class MatchBreakdown(MatchModel):
    skills: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    requirements: int = Field(ge=0, le=100)


class MatchReport(MatchModel):
    overall_score: int = Field(ge=0, le=100)
    breakdown: MatchBreakdown
    required_experience_years: float | None
    detected_experience_years: float
    experience_gap_years: float
    matched: list[RequirementMatch]
    missing: list[RequirementMatch]
    suggestions: list[str]
    review_required: Literal[True] = True
