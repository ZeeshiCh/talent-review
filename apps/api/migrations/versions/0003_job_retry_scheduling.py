"""add durable job retry scheduling"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scoring_jobs",
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("scoring_jobs", sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_scoring_jobs_retry",
        "scoring_jobs",
        ["retry_at"],
        unique=False,
        postgresql_where=sa.text("retryable"),
    )
    op.create_check_constraint(
        "ck_scoring_jobs_retry",
        "scoring_jobs",
        "(retryable AND status = 'failed' AND retry_at IS NOT NULL AND attempts < max_attempts) OR (NOT retryable AND retry_at IS NULL)",
    )


def downgrade():
    op.drop_constraint("ck_scoring_jobs_retry", "scoring_jobs", type_="check")
    op.drop_index(
        "ix_scoring_jobs_retry", table_name="scoring_jobs", postgresql_where=sa.text("retryable")
    )
    op.drop_column("scoring_jobs", "retry_at")
    op.drop_column("scoring_jobs", "retryable")
