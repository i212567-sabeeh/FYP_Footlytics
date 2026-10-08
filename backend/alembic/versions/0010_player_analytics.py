"""Player analytics metadata; movement and occupancy remain outside the database.

Revision ID: 0010_player_analytics
Revises: 0009_trajectory_cleaning
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "0010_player_analytics"
down_revision = "0009_trajectory_cleaning"
branch_labels = None
depends_on = None


@contextmanager
def _preserve_assignment_reference() -> Iterator[None]:
    # SQLite batch replacement needs this incoming FK temporarily detached.
    # Keep assignment rows and restore the constraint in the same transaction.
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
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking', "
            "'team_classification', 'coordinate_mapping', 'trajectory_cleaning', "
            "'player_analytics')",
        )
        batch.add_column(sa.Column("trajectory_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("analytics_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs WHERE job_type = 'player_analytics'"
        )
    ):
        raise RuntimeError("Cannot downgrade while player analytics jobs exist.")
    with (
        _preserve_assignment_reference(),
        op.batch_alter_table("processing_jobs") as batch,
    ):
        batch.drop_column("analytics_summary")
        batch.drop_column("trajectory_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking', "
            "'team_classification', 'coordinate_mapping', 'trajectory_cleaning')",
        )
