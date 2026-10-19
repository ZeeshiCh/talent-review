"""Explicit HR contracts; private storage paths and session hashes never serialize."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr


class User(BaseModel):
    id: UUID
    email: str
    name: str


class SessionCreated(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: User
    authentication: Literal["demo"] = "demo"


class Named(BaseModel):
    id: UUID
    name: str


class InterviewSummary(BaseModel):
    id: UUID
    role_id: UUID
    title: str
    is_active: bool


class CandidateSummary(BaseModel):
    id: UUID
    name: str
    email: str
    source_id: str | None


class ApplicationSummary(BaseModel):
    id: UUID
    candidate: CandidateSummary
    interview_id: UUID
    answered_count: int
    total_questions: int
    complete: bool


class Job(BaseModel):
    id: UUID
    answer_id: UUID
    status: Literal["queued", "scored", "failed", "needs a person"]
    attempts: int
    max_attempts: int
    retryable: bool
    retry_at: datetime | None
    error_code: str | None
    error_message: str | None
    review_reason: str | None


class SuggestionView(BaseModel):
    score: int
    reason: str
    model: str
    rubric_version: str
    prompt_version: str
    created_at: datetime


class OverrideView(BaseModel):
    id: UUID
    actor_id: UUID
    score: int
    reason: str
    created_at: datetime


class OverrideInput(Input):
    score: int = Field(strict=True, ge=1, le=4)
    reason: str = Field(min_length=1, max_length=2000)


class AnswerView(BaseModel):
    id: UUID
    source_id: str | None
    is_current: bool
    input_kind: str
    text: str | None
    audio_url: str | None
    audio_mime_type: str | None
    duration_seconds: int | None
    submitted_at: datetime
    source_submitted_at: str | None
    job: Job | None
    suggestion: SuggestionView | None
    overrides: list[OverrideView]
    effective_score: int | None
    effective_score_source: Literal["hr", "model"] | None


class ReviewQuestion(BaseModel):
    id: UUID
    number: int
    prompt: str
    rubric_version: str
    rubric: dict[str, str]
    revisions: list[AnswerView]


class Review(BaseModel):
    application: ApplicationSummary
    questions: list[ReviewQuestion]


class CandidateCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    interview_id: UUID


class InviteInput(Input):
    days: int = Field(default=7, ge=1, le=30)


class InviteView(BaseModel):
    id: UUID
    application_id: UUID
    expires_at: datetime
    revoked_at: datetime | None


class InviteCreated(InviteView):
    token: str
    personal_link: str


class RetryView(BaseModel):
    requeued: bool
    job: Job


class SystemStatus(BaseModel):
    live_scoring_configured: bool
    model: str
    job_counts: dict[str, int]
    authentication: Literal["demo"] = "demo"
