"""Match PDF snapshot metadata; documents remain in protected storage.

Revision ID: 0012_match_reports
Revises: 0011_team_tactical_analytics
"""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "0012_match_reports"
down_revision = "0011_team_tactical_analytics"
branch_labels = None
depends_on = None

PREVIOUS_TYPES = (
    "'video_preparation', 'player_detection', 'player_tracking', "
    "'team_classification', 'coordinate_mapping', 'trajectory_cleaning', "
    "'player_analytics', 'team_tactical_analytics'"
)


@contextmanager
def _preserve_assignment_reference() -> Iterator[None]:
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
            f"job_type IN ({PREVIOUS_TYPES}, 'match_report')",
        )
        batch.add_column(sa.Column("report_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("report_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM processing_jobs WHERE job_type = 'match_report'")
    ):
        raise RuntimeError("Cannot downgrade while match report jobs exist.")
    with (
        _preserve_assignment_reference(),
        op.batch_alter_table("processing_jobs") as batch,
    ):
        batch.drop_column("report_summary")
        batch.drop_column("report_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            f"job_type IN ({PREVIOUS_TYPES})",
        )
