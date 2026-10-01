from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class PlanRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=80)
    start_date: date
    end_date: date
    budget_usd: int = Field(ge=100, le=100_000)
    travelers: int = Field(default=1, ge=1, le=8)
    interests: list[str] = Field(min_length=1, max_length=8)
    origin_iata: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    pace: Literal["relaxed", "balanced", "busy"] = "balanced"

    @field_validator("destination")
    @classmethod
    def clean_destination(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(v.strip().lower() for v in values if v.strip()))
        if not cleaned or any(len(v) > 40 for v in cleaned):
            raise ValueError("Provide one to eight short interests")
        return cleaned

    @model_validator(mode="after")
    def validate_dates(self) -> PlanRequest:
        if self.start_date < datetime.now(UTC).date():
            raise ValueError("Start date must be today or later")
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        if (self.end_date - self.start_date).days > 6:
            raise ValueError("A plan can cover at most 7 days")
        if self.origin_iata:
            self.origin_iata = self.origin_iata.upper()
        return self


class Evidence(BaseModel):
    source: str
    url: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: Literal["live", "catalogue", "estimate", "unavailable"]
    note: str = ""


class Activity(BaseModel):
    name: str
    category: str
    duration_hours: float
    estimated_cost_usd: int = 0  # per traveler
    indoor: bool = False
    description: str
    map_url: str
    evidence: Evidence


class Offer(BaseModel):
    title: str
    amount_usd: int  # total group/trip for flight; group/night for hotel
    currency: str = "USD"
    status: Literal["live_offer", "planning_allowance"]
    search_url: str
    evidence: Evidence


class WeatherDay(BaseModel):
    date: date
    temperature_max_c: float | None = None
    precipitation_probability: int | None = None


class ScheduleItem(BaseModel):
    time: str
    title: str
    detail: str
    estimated_cost_usd: int  # total group
    map_url: str | None = None
    category: str


class PlanDay(BaseModel):
    date: date
    theme: str
    weather: WeatherDay | None = None
    items: list[ScheduleItem]
    estimated_cost_usd: int


class CostLine(BaseModel):
    label: str
    amount_usd: int
    basis: str
    status: Literal["live_offer", "estimate", "allowance"]


class BudgetSummary(BaseModel):
    budget_usd: int
    estimated_total_usd: int
    remaining_usd: int
    feasible: bool
    lines: list[CostLine]


class AgentTrace(BaseModel):
    agent: str
    outcome: str
    source_kind: str
    duration_ms: int


class TravelPlan(BaseModel):
    id: UUID
    created_at: datetime
    request: PlanRequest
    destination_label: str
    headline: str
    summary: str
    days: list[PlanDay]
    flight: Offer | None
    hotel: Offer
    budget: BudgetSummary
    caveats: list[str]
    trace: list[AgentTrace]
