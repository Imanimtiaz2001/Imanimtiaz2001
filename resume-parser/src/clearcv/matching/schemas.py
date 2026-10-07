from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MatchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JDRequirement(MatchModel):
    value: str = Field(min_length=1, max_length=180)
    kind: Literal["skill", "experience", "education", "responsibility"]
    required: bool = True
    evidence: str = Field(min_length=1, max_length=1000)
    weight: float = Field(default=1.0, ge=0.1, le=3.0)


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
    confidence: Literal["exact", "related", "experience", "missing"] = "missing"
    explanation: str = ""


class MatchBreakdown(MatchModel):
    skills: int = Field(ge=0, le=100)
    experience: int = Field(ge=0, le=100)
    requirements: int = Field(ge=0, le=100)
    responsibilities: int = Field(default=100, ge=0, le=100)
    education: int = Field(default=100, ge=0, le=100)


class MatchReport(MatchModel):
    overall_score: int = Field(ge=0, le=100)
    breakdown: MatchBreakdown
    required_experience_years: float | None
    detected_experience_years: float
    experience_gap_years: float
    matched: list[RequirementMatch]
    missing: list[RequirementMatch]
    suggestions: list[str]
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    summary: str = ""
    review_required: Literal[True] = True


class CandidateMatch(MatchModel):
    resume_id: str
    candidate_name: str | None
    rank: int = Field(ge=1)
    report: MatchReport


class RankingRequest(MatchModel):
    resume_ids: list[str] = Field(min_length=1, max_length=50)
    job_description: str = Field(min_length=1, max_length=30000)


class RankingReport(MatchModel):
    job_title: str | None
    candidates: list[CandidateMatch]
    review_required: Literal[True] = True
