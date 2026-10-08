"""Trajectory cleaning job metadata; raw and clean rows remain in CSV files.

Revision ID: 0009_trajectory_cleaning
Revises: 0008_coordinate_mapping
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "0009_trajectory_cleaning"
down_revision = "0008_coordinate_mapping"
branch_labels = None
depends_on = None


@contextmanager
def _preserve_assignment_reference() -> Iterator[None]:
    # SQLite replaces the parent table during a batch. Preserve child records
    # while detaching/restoring this incoming FK in the migration transaction.
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
            "'team_classification', 'coordinate_mapping', 'trajectory_cleaning')",
        )
        batch.add_column(sa.Column("coordinate_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("trajectory_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs "
            "WHERE job_type = 'trajectory_cleaning'"
        )
    ):
        raise RuntimeError("Cannot downgrade while trajectory cleaning jobs exist.")
    with (
        _preserve_assignment_reference(),
        op.batch_alter_table("processing_jobs") as batch,
    ):
        batch.drop_column("trajectory_summary")
        batch.drop_column("coordinate_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking', "
            "'team_classification', 'coordinate_mapping')",
        )
