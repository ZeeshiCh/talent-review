"""add complete hiring domain schema"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint("ck_roles_name", "roles", "length(btrim(name)) > 0")
    op.create_table(
        "candidates",
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(email)) > 0", name="ck_candidates_email"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_candidates_name"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(op.f("ix_candidates_email"), "candidates", ["email"], unique=False)
    op.create_table(
        "hr_users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(email)) > 0 AND length(btrim(name)) > 0", name="ck_hr_users_identity"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "hr_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_hr_sessions_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_hr_sessions_expiry"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["hr_users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_hr_sessions_user_id"), "hr_sessions", ["user_id"], unique=False)
    op.create_table(
        "interviews",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_interviews_title"),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_interviews_role_id"), "interviews", ["role_id"], unique=False)
    op.create_table(
        "applications",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "interview_id", name="uq_applications_candidate_interview"
        ),
        sa.UniqueConstraint("id", "interview_id", name="uq_applications_interview_scope"),
    )
    op.create_index(
        op.f("ix_applications_candidate_id"), "applications", ["candidate_id"], unique=False
    )
    op.create_index(
        op.f("ix_applications_interview_id"), "applications", ["interview_id"], unique=False
    )
    op.create_table(
        "questions",
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("rubric_version", sa.String(length=100), nullable=False),
        sa.Column("rubric_1", sa.Text(), nullable=False),
        sa.Column("rubric_2", sa.Text(), nullable=False),
        sa.Column("rubric_3", sa.Text(), nullable=False),
        sa.Column("rubric_4", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(prompt)) > 0", name="ck_questions_prompt"),
        sa.CheckConstraint(
            "length(btrim(rubric_1)) > 0 AND length(btrim(rubric_2)) > 0 AND length(btrim(rubric_3)) > 0 AND length(btrim(rubric_4)) > 0",
            name="ck_questions_rubrics",
        ),
        sa.CheckConstraint("length(btrim(rubric_version)) > 0", name="ck_questions_version"),
        sa.CheckConstraint("position BETWEEN 1 AND 6", name="ck_questions_position"),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "interview_id", name="uq_questions_interview_scope"),
        sa.UniqueConstraint("interview_id", "position", name="uq_questions_position"),
        sa.UniqueConstraint("interview_id", "source_id", name="uq_questions_source"),
    )
    op.create_table(
        "answers",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("source_submitted_at", sa.String(length=100), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("receipt", sa.Uuid(), nullable=False),
        sa.Column("input_kind", sa.String(length=16), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("audio_mime_type", sa.String(length=100), nullable=True),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "\n            (input_kind = 'text' AND length(btrim(text_content)) > 0 AND text_content IS NOT NULL\n                AND audio_path IS NULL AND audio_mime_type IS NULL AND audio_size_bytes IS NULL)\n            OR (input_kind = 'audio' AND text_content IS NULL AND audio_path IS NOT NULL\n                AND length(btrim(audio_path)) > 0 AND audio_mime_type IS NOT NULL\n                AND length(btrim(audio_mime_type)) > 0 AND audio_size_bytes > 0 AND audio_size_bytes IS NOT NULL)\n            OR (input_kind = 'missing' AND source_id IS NOT NULL AND coalesce(btrim(text_content), '') = ''\n                AND audio_path IS NULL AND audio_mime_type IS NULL AND audio_size_bytes IS NULL)\n        ",
            name="ck_answers_payload",
        ),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_answers_content_hash"),
        sa.CheckConstraint("input_kind IN ('text', 'audio', 'missing')", name="ck_answers_kind"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="ck_answers_duration"
        ),
        sa.ForeignKeyConstraint(
            ["application_id", "interview_id"],
            ["applications.id", "applications.interview_id"],
            name="fk_answers_application_scope",
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "interview_id"],
            ["questions.id", "questions.interview_id"],
            name="fk_answers_question_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", "question_id", "content_hash", name="uq_answers_content"
        ),
        sa.UniqueConstraint("id", "application_id", name="uq_answers_application_scope"),
        sa.UniqueConstraint("receipt"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(op.f("ix_answers_application_id"), "answers", ["application_id"], unique=False)
    op.create_index(op.f("ix_answers_interview_id"), "answers", ["interview_id"], unique=False)
    op.create_index(op.f("ix_answers_question_id"), "answers", ["question_id"], unique=False)
    op.create_index(
        "uq_answers_current",
        "answers",
        ["application_id", "question_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "invitations",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_invitations_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_invitations_expiry"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "application_id", name="uq_invitations_application_scope"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_invitations_application_id"), "invitations", ["application_id"], unique=False
    )
    op.create_table(
        "overrides",
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(reason)) BETWEEN 1 AND 2000", name="ck_overrides_reason"),
        sa.CheckConstraint("score BETWEEN 1 AND 4", name="ck_overrides_score"),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["hr_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_overrides_actor_id"), "overrides", ["actor_id"], unique=False)
    op.create_index(
        "ix_overrides_answer_history", "overrides", ["answer_id", "created_at", "id"], unique=False
    )
    op.create_table(
        "scoring_jobs",
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR (status = 'queued' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_scoring_jobs_lease",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL AND length(btrim(error_code)) > 0 AND error_message IS NOT NULL AND length(btrim(error_message)) > 0) OR (status <> 'failed' AND error_code IS NULL AND error_message IS NULL)",
            name="ck_scoring_jobs_failure",
        ),
        sa.CheckConstraint(
            "(status = 'needs a person' AND review_reason IS NOT NULL AND length(btrim(review_reason)) > 0) OR (status <> 'needs a person' AND review_reason IS NULL)",
            name="ck_scoring_jobs_review",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'scored', 'failed', 'needs a person')",
            name="ck_scoring_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0 AND max_attempts > 0", name="ck_scoring_jobs_attempts"),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id"),
        sa.UniqueConstraint("id", "answer_id", name="uq_scoring_jobs_answer_scope"),
    )
    op.create_index(
        "ix_scoring_jobs_poll",
        "scoring_jobs",
        ["status", "available_at", "created_at"],
        unique=False,
    )
    op.create_table(
        "submission_keys",
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'", name="ck_submission_keys_payload_hash"
        ),
        sa.CheckConstraint("length(btrim(idempotency_key)) > 0", name="ck_submission_keys_key"),
        sa.ForeignKeyConstraint(
            ["answer_id", "application_id"],
            ["answers.id", "answers.application_id"],
            name="fk_submission_keys_answer_scope",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id", "application_id"],
            ["invitations.id", "invitations.application_id"],
            name="fk_submission_keys_invitation_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invitation_id", "idempotency_key", name="uq_submission_keys_invitation_key"
        ),
    )
    op.create_index(
        op.f("ix_submission_keys_answer_id"), "submission_keys", ["answer_id"], unique=False
    )
    op.create_index(
        op.f("ix_submission_keys_application_id"),
        "submission_keys",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_submission_keys_invitation_id"), "submission_keys", ["invitation_id"], unique=False
    )
    op.create_table(
        "suggestions",
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("response_id", sa.String(length=200), nullable=False),
        sa.Column("rubric_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(model)) > 0 AND length(btrim(response_id)) > 0 AND length(btrim(rubric_version)) > 0 AND length(btrim(prompt_version)) > 0",
            name="ck_suggestions_metadata",
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 2000", name="ck_suggestions_reason"
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 4", name="ck_suggestions_score"),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "answer_id"],
            ["scoring_jobs.id", "scoring_jobs.answer_id"],
            name="fk_suggestions_job_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id"),
        sa.UniqueConstraint("job_id"),
    )


def downgrade():
    op.drop_constraint("ck_roles_name", "roles", type_="check")
    op.drop_table("suggestions")
    op.drop_index(op.f("ix_submission_keys_invitation_id"), table_name="submission_keys")
    op.drop_index(op.f("ix_submission_keys_application_id"), table_name="submission_keys")
    op.drop_index(op.f("ix_submission_keys_answer_id"), table_name="submission_keys")
    op.drop_table("submission_keys")
    op.drop_index("ix_scoring_jobs_poll", table_name="scoring_jobs")
    op.drop_table("scoring_jobs")
    op.drop_index("ix_overrides_answer_history", table_name="overrides")
    op.drop_index(op.f("ix_overrides_actor_id"), table_name="overrides")
    op.drop_table("overrides")
    op.drop_index(op.f("ix_invitations_application_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index(
        "uq_answers_current", table_name="answers", postgresql_where=sa.text("is_current")
    )
    op.drop_index(op.f("ix_answers_question_id"), table_name="answers")
    op.drop_index(op.f("ix_answers_interview_id"), table_name="answers")
    op.drop_index(op.f("ix_answers_application_id"), table_name="answers")
    op.drop_table("answers")
    op.drop_table("questions")
    op.drop_index(op.f("ix_applications_interview_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_candidate_id"), table_name="applications")
    op.drop_table("applications")
    op.drop_index(op.f("ix_interviews_role_id"), table_name="interviews")
    op.drop_table("interviews")
    op.drop_index(op.f("ix_hr_sessions_user_id"), table_name="hr_sessions")
    op.drop_table("hr_sessions")
    op.drop_table("hr_users")
    op.drop_index(op.f("ix_candidates_email"), table_name="candidates")
    op.drop_table("candidates")
