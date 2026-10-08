"""Add tracking jobs and small detection provenance/tracking summaries.

Revision ID: 0006_player_tracking
Revises: 0005_player_detection
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_player_tracking"
down_revision = "0005_player_detection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking')",
        )
        batch.add_column(sa.Column("detection_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("tracking_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs WHERE job_type = 'player_tracking'"
        )
    ):
        raise RuntimeError("Cannot downgrade while player tracking jobs exist.")
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_column("tracking_summary")
        batch.drop_column("detection_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection')",
        )
