"""Team tactical analytics metadata; frame geometry stays in protected CSV bundles.

Revision ID: 0011_team_tactical_analytics
Revises: 0010_player_analytics
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "0011_team_tactical_analytics"
down_revision = "0010_player_analytics"
branch_labels = None
depends_on = None

PREVIOUS_TYPES = (
    "'video_preparation', 'player_detection', 'player_tracking', "
    "'team_classification', 'coordinate_mapping', 'trajectory_cleaning', "
    "'player_analytics'"
)


@contextmanager
def _preserve_assignment_reference() -> Iterator[None]:
    # SQLite batch replacement needs the incoming composite FK detached, then
    # restored in this transaction; existing assignments and overrides are retained.
    sqlite = op.get_bind().dialect.name == "sqlite"
    name = "fk_track_team_assignments_tracking_match"
    if sqlite:
        with op.batch_alter_table("track_team_assignments") as batch:
            batch.drop_constraint(name, type_="foreignkey")
    yield
    if sqlite:
        with op.batch_alter_table("track_team_assignments") as batch:
            batch.create_foreign_key(
                name,
                "processing_jobs",
                ["match_id", "tracking_job_id"],
                ["match_id", "id"],
                ondelete="RESTRICT",
            )


def upgrade() -> None:
    with (
        _preserve_assignment_reference(),
        op.batch_alter_table("processing_jobs") as batch,
    ):
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            f"job_type IN ({PREVIOUS_TYPES}, 'team_tactical_analytics')",
        )
        batch.add_column(sa.Column("assignment_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("tactics_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs "
            "WHERE job_type = 'team_tactical_analytics'"
        )
    ):
        raise RuntimeError("Cannot downgrade while team tactical analytics jobs exist.")
    with (
        _preserve_assignment_reference(),
        op.batch_alter_table("processing_jobs") as batch,
    ):
        batch.drop_column("tactics_summary")
        batch.drop_column("assignment_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"), f"job_type IN ({PREVIOUS_TYPES})"
        )
