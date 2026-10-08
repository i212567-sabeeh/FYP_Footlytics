from enum import StrEnum


class JobType(StrEnum):
    VIDEO_PREPARATION = "video_preparation"
    PLAYER_DETECTION = "player_detection"
    PLAYER_TRACKING = "player_tracking"
    TEAM_CLASSIFICATION = "team_classification"
    COORDINATE_MAPPING = "coordinate_mapping"
    TRAJECTORY_CLEANING = "trajectory_cleaning"
    PLAYER_ANALYTICS = "player_analytics"
    TEAM_TACTICAL_ANALYTICS = "team_tactical_analytics"
    MATCH_REPORT = "match_report"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)
RETRYABLE_JOB_STATUSES = (JobStatus.FAILED, JobStatus.CANCELLED)
