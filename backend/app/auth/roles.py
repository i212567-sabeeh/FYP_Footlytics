from enum import StrEnum
from typing import Literal


class RoleName(StrEnum):
    ADMIN = "admin"
    COACH = "coach"
    ANALYST = "analyst"
    PLAYER = "player"
    CLUB_MANAGEMENT = "club_management"


# A public signup may request one of these roles; it never grants access itself.
SignupRole = Literal[
    RoleName.COACH, RoleName.ANALYST, RoleName.PLAYER, RoleName.CLUB_MANAGEMENT
]


ROLE_DISPLAY_NAMES: dict[RoleName, str] = {
    RoleName.ADMIN: "Admin",
    RoleName.COACH: "Coach",
    RoleName.ANALYST: "Analyst",
    RoleName.PLAYER: "Player",
    RoleName.CLUB_MANAGEMENT: "Club Management",
}
