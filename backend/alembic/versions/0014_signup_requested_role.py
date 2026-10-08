"""Record the non-admin role requested at signup, preserving legacy requests."""

import sqlalchemy as sa

from alembic import op

revision = "0014_signup_requested_role"
down_revision = "0013_signup_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old requests never supplied a role. Keep NULL rather than inventing one;
    # the public request schema requires a non-admin role for all new signups.
    with op.batch_alter_table("signup_requests") as batch:
        batch.add_column(sa.Column("requested_role", sa.String(16), nullable=True))
        batch.create_check_constraint(
            op.f("ck_signup_requests_valid_requested_role"),
            "requested_role IS NULL OR requested_role IN "
            "('coach', 'analyst', 'player', 'club_management')",
        )


def downgrade() -> None:
    with op.batch_alter_table("signup_requests") as batch:
        batch.drop_constraint(
            op.f("ck_signup_requests_valid_requested_role"), type_="check"
        )
        batch.drop_column("requested_role")
