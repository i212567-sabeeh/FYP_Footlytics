"""clubs_teams_players_matches

Revision ID: 0002_clubs_teams_players_matches
Revises: 0001_users_and_roles
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_clubs_teams_players_matches"
down_revision: str | Sequence[str] | None = "0001_users_and_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("short_name", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clubs")),
        sa.UniqueConstraint("name_key", name=op.f("uq_clubs_name_key")),
    )
    op.create_table(
        "club_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name=op.f("fk_club_memberships_club_id_clubs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_club_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_club_memberships")),
        sa.UniqueConstraint(
            "club_id", "user_id", name=op.f("uq_club_memberships_club_id")
        ),
    )
    with op.batch_alter_table("club_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_club_memberships_club_id"), ["club_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_club_memberships_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("preferred_position", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "preferred_position IS NULL OR preferred_position IN "
            "('goalkeeper', 'defender', 'midfielder', 'forward', 'other')",
            name=op.f("ck_players_position"),
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name=op.f("fk_players_club_id_clubs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_players_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
        sa.UniqueConstraint("club_id", "id", name=op.f("uq_players_club_id")),
        sa.UniqueConstraint("user_id", name=op.f("uq_players_user_id")),
    )
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_players_club_id"), ["club_id"], unique=False
        )

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("short_name", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name=op.f("fk_teams_club_id_clubs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("club_id", "id", name=op.f("uq_teams_club_id")),
        sa.UniqueConstraint("club_id", "name_key", name="uq_teams_club_name"),
    )
    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_teams_club_id"), ["club_id"], unique=False)

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("team_a_id", sa.Integer(), nullable=False),
        sa.Column("team_b_id", sa.Integer(), nullable=False),
        sa.Column("match_format", sa.String(length=10), nullable=False),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pitch_length_metres", sa.Float(), nullable=False),
        sa.Column("pitch_width_metres", sa.Float(), nullable=False),
        sa.Column("venue", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "match_format IN ('11v11', '5v5')", name=op.f("ck_matches_format")
        ),
        sa.CheckConstraint(
            "pitch_length_metres >= 10 AND pitch_length_metres <= 150",
            name=op.f("ck_matches_pitch_length"),
        ),
        sa.CheckConstraint(
            "pitch_length_metres >= pitch_width_metres",
            name=op.f("ck_matches_pitch_axes"),
        ),
        sa.CheckConstraint(
            "pitch_width_metres >= 5 AND pitch_width_metres <= 100",
            name=op.f("ck_matches_pitch_width"),
        ),
        sa.CheckConstraint(
            "team_a_id <> team_b_id", name=op.f("ck_matches_different_teams")
        ),
        sa.ForeignKeyConstraint(
            ["club_id", "team_a_id"],
            ["teams.club_id", "teams.id"],
            name="fk_match_team_a_club",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["club_id", "team_b_id"],
            ["teams.club_id", "teams.id"],
            name="fk_match_team_b_club",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name=op.f("fk_matches_club_id_clubs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_matches_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
    )
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_matches_club_id"), ["club_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_matches_match_date"), ["match_date"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_matches_team_a_id"), ["team_a_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_matches_team_b_id"), ["team_b_id"], unique=False
        )

    op.create_table(
        "squad_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("shirt_number", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT is_active OR left_at IS NULL",
            name=op.f("ck_squad_memberships_active_period"),
        ),
        sa.CheckConstraint(
            "left_at IS NULL OR joined_at IS NULL OR left_at >= joined_at",
            name=op.f("ck_squad_memberships_period_order"),
        ),
        sa.CheckConstraint(
            "shirt_number IS NULL OR (shirt_number >= 1 AND shirt_number <= 99)",
            name=op.f("ck_squad_memberships_shirt_number"),
        ),
        sa.ForeignKeyConstraint(
            ["club_id", "player_id"],
            ["players.club_id", "players.id"],
            name="fk_squad_player_club",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["club_id", "team_id"],
            ["teams.club_id", "teams.id"],
            name="fk_squad_team_club",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_squad_memberships")),
    )
    with op.batch_alter_table("squad_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_squad_memberships_club_id"), ["club_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_squad_memberships_player_id"), ["player_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_squad_memberships_team_id"), ["team_id"], unique=False
        )
        batch_op.create_index(
            "uq_squad_active_player",
            ["team_id", "player_id"],
            unique=True,
            sqlite_where=sa.text("is_active"),
            postgresql_where=sa.text("is_active"),
        )
        batch_op.create_index(
            "uq_squad_active_shirt",
            ["team_id", "shirt_number"],
            unique=True,
            sqlite_where=sa.text("is_active AND shirt_number IS NOT NULL"),
            postgresql_where=sa.text("is_active AND shirt_number IS NOT NULL"),
        )


def downgrade() -> None:

    with op.batch_alter_table("squad_memberships", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_squad_active_shirt",
            sqlite_where=sa.text("is_active AND shirt_number IS NOT NULL"),
            postgresql_where=sa.text("is_active AND shirt_number IS NOT NULL"),
        )
        batch_op.drop_index(
            "uq_squad_active_player",
            sqlite_where=sa.text("is_active"),
            postgresql_where=sa.text("is_active"),
        )
        batch_op.drop_index(batch_op.f("ix_squad_memberships_team_id"))
        batch_op.drop_index(batch_op.f("ix_squad_memberships_player_id"))
        batch_op.drop_index(batch_op.f("ix_squad_memberships_club_id"))

    op.drop_table("squad_memberships")
    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_matches_team_b_id"))
        batch_op.drop_index(batch_op.f("ix_matches_team_a_id"))
        batch_op.drop_index(batch_op.f("ix_matches_match_date"))
        batch_op.drop_index(batch_op.f("ix_matches_club_id"))

    op.drop_table("matches")
    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_teams_club_id"))

    op.drop_table("teams")
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_players_club_id"))

    op.drop_table("players")
    with op.batch_alter_table("club_memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_club_memberships_user_id"))
        batch_op.drop_index(batch_op.f("ix_club_memberships_club_id"))

    op.drop_table("club_memberships")
    op.drop_table("clubs")
