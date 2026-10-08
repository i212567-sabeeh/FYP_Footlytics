"""Pending signup credentials never grant access to the application."""

from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UTCDateTime, utc_now

SignupStatus = Literal["pending", "approved", "rejected"]


class SignupRequest(Base):
    __tablename__ = "signup_requests"
    __table_args__ = (
        CheckConstraint(
            "requested_role IS NULL OR requested_role IN "
            "('coach', 'analyst', 'player', 'club_management')",
            name="valid_requested_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="valid_status"
        ),
        CheckConstraint(
            "(status = 'pending' AND hashed_password IS NOT NULL) OR "
            "(status != 'pending' AND hashed_password IS NULL)",
            name="pending_credentials",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # NULL is reserved for requests created before role selection was added.
    requested_role: Mapped[str | None] = mapped_column(String(16))
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
