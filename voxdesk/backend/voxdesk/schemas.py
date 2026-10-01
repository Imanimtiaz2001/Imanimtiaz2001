from typing import Literal

from pydantic import BaseModel, Field


class ModelAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=1800)
    source_ids: list[str] = Field(max_length=6)
    abstained: bool


class Source(BaseModel):
    id: str
    document_id: str
    name: str
    excerpt: str
    score: float


class Answer(BaseModel):
    text: str
    sources: list[Source]
    abstained: bool


class TurnView(BaseModel):
    id: str
    request_id: str
    transcript: str
    answer: Answer
    timings: dict[str, float]
    audio_url: str | None
    warning: str | None
    mode: Literal["general", "knowledge"]
    created_at: str


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)
