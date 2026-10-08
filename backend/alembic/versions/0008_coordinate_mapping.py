"""Coordinate mapping jobs; coordinate rows remain in attempt-specific CSVs.

Revision ID: 0008_coordinate_mapping
Revises: 0007_team_classification
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "0008_coordinate_mapping"
down_revision = "0007_team_classification"
branch_labels = None
depends_on = None


@contextmanager
def _preserve_assignment_reference() -> Iterator[None]:
    # SQLite batch alteration replaces the parent table. Detach its incoming FK
    # with data-preserving child batches, then restore it in this transaction.
    # Foreign-key enforcement stays ON, including all other constraints.
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
            "'team_classification', 'coordinate_mapping')",
        )
        batch.add_column(sa.Column("coordinate_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs WHERE job_type = 'coordinate_mapping'"
        )
    ):
        raise RuntimeError("Cannot downgrade while coordinate mapping jobs exist.")
    with (
        _preserve_assignment_reference(),
        op.batch_alter_table("processing_jobs") as batch,
    ):
        batch.drop_column("coordinate_summary")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking', "
            "'team_classification')",
        )
