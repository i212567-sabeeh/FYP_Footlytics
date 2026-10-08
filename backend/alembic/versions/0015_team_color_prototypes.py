"""Versioned team-color prototypes and per-result classification provenance."""

import sqlalchemy as sa

from alembic import op

revision = "0015_team_color_prototypes"
down_revision = "0014_signup_requested_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_color_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.Integer(),
            sa.ForeignKey("match_videos.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tracking_job_id", sa.Integer(), nullable=False),
        sa.Column("tracking_version", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("samples", sa.JSON(), nullable=False),
        sa.Column("prototypes", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["match_id", "tracking_job_id"],
            ["processing_jobs.match_id", "processing_jobs.id"],
            name="fk_team_color_sets_tracking_match",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_team_color_sets_match_id", "team_color_sets", ["match_id"])
    with op.batch_alter_table("processing_jobs") as batch:
        batch.add_column(sa.Column("team_color_snapshot", sa.JSON(), nullable=True))
    with op.batch_alter_table("track_team_assignments") as batch:
        batch.add_column(
            sa.Column(
                "classification_mode",
                sa.String(16),
                nullable=False,
                server_default="automatic",
            )
        )
        batch.add_column(
            sa.Column("classification_provenance", sa.JSON(), nullable=True)
        )
        batch.create_check_constraint(
            op.f("ck_track_team_assignments_classification_mode"),
            "classification_mode IN ('automatic', 'user_seeded')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM team_color_sets")):
        raise RuntimeError(
            "Cannot downgrade while team-color prototype history exists."
        )
    if bind.scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs WHERE team_color_snapshot IS NOT NULL"
        )
    ):
        raise RuntimeError("Cannot downgrade while team-color job history exists.")
    # Remove the new incoming reference first. SQLite batch replacement of the
    # parent jobs table also needs the existing assignment FK detached/restored,
    # preserving every assignment and manual override, as in earlier migrations.
    op.drop_index("ix_team_color_sets_match_id", table_name="team_color_sets")
    op.drop_table("team_color_sets")
    sqlite = bind.dialect.name == "sqlite"
    reference = "fk_track_team_assignments_tracking_match"
    with op.batch_alter_table("track_team_assignments") as batch:
        if sqlite:
            batch.drop_constraint(reference, type_="foreignkey")
        batch.drop_constraint(
            op.f("ck_track_team_assignments_classification_mode"), type_="check"
        )
        batch.drop_column("classification_provenance")
        batch.drop_column("classification_mode")
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_column("team_color_snapshot")
    if sqlite:
        with op.batch_alter_table("track_team_assignments") as batch:
            batch.create_foreign_key(
                reference,
                "processing_jobs",
                ["match_id", "tracking_job_id"],
                ["match_id", "id"],
                ondelete="RESTRICT",
            )
