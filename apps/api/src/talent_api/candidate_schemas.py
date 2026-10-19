"""Explicit candidate-only contracts; never serialize domain/score ORM rows."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TextSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(
        min_length=1,
        max_length=50000,
        examples=["I built a reconciliation report and reduced weekly review effort."],
    )

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("An answer must contain text")
        return value


class Receipt(BaseModel):
    accepted: Literal[True] = True
    receipt: UUID
    question_id: UUID
    input_kind: Literal["text", "audio"]
    submitted_at: datetime


class QuestionPublic(BaseModel):
    id: UUID
    number: int
    prompt: str


class QuestionProgress(BaseModel):
    question_id: UUID
    answered: bool
    receipt: Receipt | None = None


class Progress(BaseModel):
    total_questions: int
    answered_count: int
    complete: bool
    next_question_id: UUID | None
    questions: list[QuestionProgress]


class InterviewPublic(BaseModel):
    title: str
    role: str
    questions: list[QuestionPublic]
    progress: Progress
