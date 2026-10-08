"""Add administrator-reviewed signup requests without changing existing accounts."""

import sqlalchemy as sa

from alembic import op

revision = "0013_signup_requests"
down_revision = "0012_match_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signup_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_user_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signup_requests")),
        sa.UniqueConstraint("email", name=op.f("uq_signup_requests_email")),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_signup_requests_valid_status"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND hashed_password IS NOT NULL) OR "
            "(status != 'pending' AND hashed_password IS NULL)",
            name=op.f("ck_signup_requests_pending_credentials"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f("fk_signup_requests_reviewed_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name=op.f("fk_signup_requests_approved_user_id_users"),
        ),
    )
    op.create_index(op.f("ix_signup_requests_status"), "signup_requests", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_signup_requests_status"), table_name="signup_requests")
    op.drop_table("signup_requests")
