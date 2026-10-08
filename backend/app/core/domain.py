"""Controlled domain values and broad, format-independent validation bounds."""

from enum import StrEnum


class MatchFormat(StrEnum):
    ELEVEN = "11v11"
    FIVE = "5v5"


class Position(StrEnum):
    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    MIDFIELDER = "midfielder"
    FORWARD = "forward"
    OTHER = "other"


MIN_PITCH_LENGTH = 10
MAX_PITCH_LENGTH = 150
MIN_PITCH_WIDTH = 5
MAX_PITCH_WIDTH = 100
