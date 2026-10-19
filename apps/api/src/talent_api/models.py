"""Persistent domain model. API authorization and state transitions belong in services.

Answer rows are immutable revisions; is_current selects the effective revision.
Foreign keys restrict deletion by default to preserve review/audit history.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Role(Identity, Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="ck_roles_name"),)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class Candidate(Identity, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_candidates_name"),
        CheckConstraint("length(btrim(email)) > 0", name="ck_candidates_email"),
    )
    source_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), index=True)


class Interview(Identity, Base):
    __tablename__ = "interviews"
    __table_args__ = (CheckConstraint("length(btrim(title)) > 0", name="ck_interviews_title"),)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Question(Identity, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("interview_id", "position", name="uq_questions_position"),
        UniqueConstraint("interview_id", "source_id", name="uq_questions_source"),
        UniqueConstraint("id", "interview_id", name="uq_questions_interview_scope"),
        CheckConstraint("position BETWEEN 1 AND 6", name="ck_questions_position"),
        CheckConstraint("length(btrim(prompt)) > 0", name="ck_questions_prompt"),
        CheckConstraint("length(btrim(rubric_version)) > 0", name="ck_questions_version"),
        CheckConstraint(
            " AND ".join(f"length(btrim(rubric_{i})) > 0" for i in range(1, 5)),
            name="ck_questions_rubrics",
        ),
    )
    interview_id: Mapped[UUID] = mapped_column(ForeignKey("interviews.id"))
    source_id: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(Text)
    rubric_version: Mapped[str] = mapped_column(String(100))
    rubric_1: Mapped[str] = mapped_column(Text)
    rubric_2: Mapped[str] = mapped_column(Text)
    rubric_3: Mapped[str] = mapped_column(Text)
    rubric_4: Mapped[str] = mapped_column(Text)


class Application(Identity, Base):
    """Candidate participation in an interview; permits applications to multiple roles."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "interview_id", name="uq_applications_candidate_interview"
        ),
        UniqueConstraint("id", "interview_id", name="uq_applications_interview_scope"),
    )
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("candidates.id"), index=True)
    interview_id: Mapped[UUID] = mapped_column(ForeignKey("interviews.id"), index=True)


class Invitation(Identity, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint("id", "application_id", name="uq_invitations_application_scope"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_invitations_token_hash"),
        CheckConstraint("expires_at > created_at", name="ck_invitations_expiry"),
    )
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Answer(Identity, Base):
    __tablename__ = "answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "interview_id"],
            ["applications.id", "applications.interview_id"],
            name="fk_answers_application_scope",
        ),
        ForeignKeyConstraint(
            ["question_id", "interview_id"],
            ["questions.id", "questions.interview_id"],
            name="fk_answers_question_scope",
        ),
        UniqueConstraint("id", "application_id", name="uq_answers_application_scope"),
        UniqueConstraint(
            "application_id", "question_id", "content_hash", name="uq_answers_content"
        ),
        Index(
            "uq_answers_current",
            "application_id",
            "question_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_answers_content_hash"),
        CheckConstraint("input_kind IN ('text', 'audio', 'missing')", name="ck_answers_kind"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="ck_answers_duration"
        ),
        CheckConstraint(
            """
            (input_kind = 'text' AND length(btrim(text_content)) > 0 AND text_content IS NOT NULL
                AND audio_path IS NULL AND audio_mime_type IS NULL AND audio_size_bytes IS NULL)
            OR (input_kind = 'audio' AND text_content IS NULL AND audio_path IS NOT NULL
                AND length(btrim(audio_path)) > 0 AND audio_mime_type IS NOT NULL
                AND length(btrim(audio_mime_type)) > 0 AND audio_size_bytes > 0 AND audio_size_bytes IS NOT NULL)
            OR (input_kind = 'missing' AND source_id IS NOT NULL AND coalesce(btrim(text_content), '') = ''
                AND audio_path IS NULL AND audio_mime_type IS NULL AND audio_size_bytes IS NULL)
        """,
            name="ck_answers_payload",
        ),
    )
    application_id: Mapped[UUID] = mapped_column(index=True)
    interview_id: Mapped[UUID] = mapped_column(index=True)
    question_id: Mapped[UUID] = mapped_column(index=True)
    source_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    source_submitted_at: Mapped[str | None] = mapped_column(String(100))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    receipt: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    input_kind: Mapped[str] = mapped_column(String(16))
    text_content: Mapped[str | None] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    audio_mime_type: Mapped[str | None] = mapped_column(String(100))
    audio_size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class SubmissionKey(Identity, Base):
    __tablename__ = "submission_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invitation_id", "application_id"],
            ["invitations.id", "invitations.application_id"],
            name="fk_submission_keys_invitation_scope",
        ),
        ForeignKeyConstraint(
            ["answer_id", "application_id"],
            ["answers.id", "answers.application_id"],
            name="fk_submission_keys_answer_scope",
        ),
        UniqueConstraint(
            "invitation_id", "idempotency_key", name="uq_submission_keys_invitation_key"
        ),
        CheckConstraint("length(btrim(idempotency_key)) > 0", name="ck_submission_keys_key"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_submission_keys_payload_hash"),
    )
    invitation_id: Mapped[UUID] = mapped_column(index=True)
    application_id: Mapped[UUID] = mapped_column(index=True)
    answer_id: Mapped[UUID] = mapped_column(index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))


class ScoringJob(Identity, Base):
    __tablename__ = "scoring_jobs"
    __table_args__ = (
        UniqueConstraint("id", "answer_id", name="uq_scoring_jobs_answer_scope"),
        CheckConstraint(
            "status IN ('queued', 'scored', 'failed', 'needs a person')",
            name="ck_scoring_jobs_status",
        ),
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="ck_scoring_jobs_attempts"),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR (status = 'queued' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_scoring_jobs_lease",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL AND length(btrim(error_code)) > 0 AND error_message IS NOT NULL AND length(btrim(error_message)) > 0) OR (status <> 'failed' AND error_code IS NULL AND error_message IS NULL)",
            name="ck_scoring_jobs_failure",
        ),
        CheckConstraint(
            "(status = 'needs a person' AND review_reason IS NOT NULL AND length(btrim(review_reason)) > 0) OR (status <> 'needs a person' AND review_reason IS NULL)",
            name="ck_scoring_jobs_review",
        ),
        CheckConstraint(
            "(retryable AND status = 'failed' AND retry_at IS NOT NULL AND attempts < max_attempts) OR (NOT retryable AND retry_at IS NULL)",
            name="ck_scoring_jobs_retry",
        ),
        Index("ix_scoring_jobs_retry", "retry_at", postgresql_where=text("retryable")),
        Index("ix_scoring_jobs_poll", "status", "available_at", "created_at"),
    )
    answer_id: Mapped[UUID] = mapped_column(ForeignKey("answers.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="3")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_token: Mapped[UUID | None] = mapped_column()
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retryable: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    review_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Suggestion(Identity, Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "answer_id"],
            ["scoring_jobs.id", "scoring_jobs.answer_id"],
            name="fk_suggestions_job_scope",
        ),
        CheckConstraint("score BETWEEN 1 AND 4", name="ck_suggestions_score"),
        CheckConstraint("length(btrim(reason)) BETWEEN 1 AND 2000", name="ck_suggestions_reason"),
        CheckConstraint(
            "length(btrim(model)) > 0 AND length(btrim(response_id)) > 0 AND length(btrim(rubric_version)) > 0 AND length(btrim(prompt_version)) > 0",
            name="ck_suggestions_metadata",
        ),
    )
    answer_id: Mapped[UUID] = mapped_column(ForeignKey("answers.id"), unique=True)
    job_id: Mapped[UUID] = mapped_column(unique=True)
    score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(200))
    response_id: Mapped[str] = mapped_column(String(200))
    rubric_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))


class HRUser(Identity, Base):
    __tablename__ = "hr_users"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(email)) > 0 AND length(btrim(name)) > 0", name="ck_hr_users_identity"
        ),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class HRSession(Identity, Base):
    __tablename__ = "hr_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_hr_sessions_token_hash"),
        CheckConstraint("expires_at > created_at", name="ck_hr_sessions_expiry"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("hr_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Override(Identity, Base):
    __tablename__ = "overrides"
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 4", name="ck_overrides_score"),
        CheckConstraint("length(btrim(reason)) BETWEEN 1 AND 2000", name="ck_overrides_reason"),
        Index("ix_overrides_answer_history", "answer_id", "created_at", "id"),
    )
    answer_id: Mapped[UUID] = mapped_column(ForeignKey("answers.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("hr_users.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
