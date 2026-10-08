from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class Club(Timestamps, Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200), unique=True)
    short_name: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    memberships: Mapped[list["ClubMembership"]] = relationship(
        back_populates="club", passive_deletes="all"
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="club", passive_deletes="all"
    )
    players: Mapped[list["Player"]] = relationship(
        back_populates="club", passive_deletes="all"
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="club", passive_deletes="all"
    )


class ClubMembership(Base):
    __tablename__ = "club_memberships"
    __table_args__ = (UniqueConstraint("club_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    club: Mapped[Club] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(
        back_populates="club_memberships", lazy="joined"
    )


class Team(Timestamps, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("club_id", "name_key", name="uq_teams_club_name"),
        UniqueConstraint("club_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    club: Mapped[Club] = relationship(back_populates="teams", lazy="joined")
    squad_memberships: Mapped[list["SquadMembership"]] = relationship(
        back_populates="team",
        foreign_keys="SquadMembership.team_id",
        passive_deletes="all",
    )
    matches_as_a: Mapped[list["Match"]] = relationship(
        back_populates="team_a", foreign_keys="Match.team_a_id", passive_deletes="all"
    )
    matches_as_b: Mapped[list["Match"]] = relationship(
        back_populates="team_b", foreign_keys="Match.team_b_id", passive_deletes="all"
    )


class Player(Timestamps, Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("club_id", "id"),
        CheckConstraint(
            "preferred_position IS NULL OR preferred_position IN "
            "('goalkeeper', 'defender', 'midfielder', 'forward', 'other')",
            name="position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    preferred_position: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    club: Mapped[Club] = relationship(back_populates="players", lazy="joined")
    linked_user: Mapped["User | None"] = relationship(
        back_populates="player_profile", lazy="joined"
    )
    squad_memberships: Mapped[list["SquadMembership"]] = relationship(
        back_populates="player",
        foreign_keys="SquadMembership.player_id",
        passive_deletes="all",
    )


class SquadMembership(Timestamps, Base):
    __tablename__ = "squad_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["club_id", "team_id"],
            ["teams.club_id", "teams.id"],
            ondelete="RESTRICT",
            name="fk_squad_team_club",
        ),
        ForeignKeyConstraint(
            ["club_id", "player_id"],
            ["players.club_id", "players.id"],
            ondelete="RESTRICT",
            name="fk_squad_player_club",
        ),
        CheckConstraint(
            "shirt_number IS NULL OR (shirt_number >= 1 AND shirt_number <= 99)",
            name="shirt_number",
        ),
        CheckConstraint("NOT is_active OR left_at IS NULL", name="active_period"),
        CheckConstraint(
            "left_at IS NULL OR joined_at IS NULL OR left_at >= joined_at",
            name="period_order",
        ),
        Index(
            "uq_squad_active_player",
            "team_id",
            "player_id",
            unique=True,
            sqlite_where=text("is_active"),
            postgresql_where=text("is_active"),
        ),
        Index(
            "uq_squad_active_shirt",
            "team_id",
            "shirt_number",
            unique=True,
            sqlite_where=text("is_active AND shirt_number IS NOT NULL"),
            postgresql_where=text("is_active AND shirt_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(Integer, index=True)
    team_id: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[int] = mapped_column(Integer, index=True)
    shirt_number: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    joined_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    team: Mapped[Team] = relationship(
        back_populates="squad_memberships", foreign_keys=[team_id], lazy="joined"
    )
    player: Mapped[Player] = relationship(
        back_populates="squad_memberships", foreign_keys=[player_id], lazy="joined"
    )


class Match(Timestamps, Base):
    __tablename__ = "matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["club_id", "team_a_id"],
            ["teams.club_id", "teams.id"],
            ondelete="RESTRICT",
            name="fk_match_team_a_club",
        ),
        ForeignKeyConstraint(
            ["club_id", "team_b_id"],
            ["teams.club_id", "teams.id"],
            ondelete="RESTRICT",
            name="fk_match_team_b_club",
        ),
        CheckConstraint("team_a_id <> team_b_id", name="different_teams"),
        CheckConstraint("match_format IN ('11v11', '5v5')", name="format"),
        CheckConstraint(
            "pitch_length_metres >= 10 AND pitch_length_metres <= 150",
            name="pitch_length",
        ),
        CheckConstraint(
            "pitch_width_metres >= 5 AND pitch_width_metres <= 100", name="pitch_width"
        ),
        CheckConstraint("pitch_length_metres >= pitch_width_metres", name="pitch_axes"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    team_a_id: Mapped[int] = mapped_column(Integer, index=True)
    team_b_id: Mapped[int] = mapped_column(Integer, index=True)
    match_format: Mapped[str] = mapped_column(String(10))
    match_date: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    pitch_length_metres: Mapped[float] = mapped_column(Float)
    pitch_width_metres: Mapped[float] = mapped_column(Float)
    venue: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    club: Mapped[Club] = relationship(back_populates="matches", lazy="joined")
    team_a: Mapped[Team] = relationship(
        back_populates="matches_as_a", foreign_keys=[team_a_id], lazy="joined"
    )
    team_b: Mapped[Team] = relationship(
        back_populates="matches_as_b", foreign_keys=[team_b_id], lazy="joined"
    )
    created_by: Mapped["User"] = relationship(
        back_populates="created_matches", lazy="joined"
    )
