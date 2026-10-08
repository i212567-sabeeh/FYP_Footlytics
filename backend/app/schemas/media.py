from datetime import datetime

from app.core.jobs import JobStatus, JobType
from app.schemas.coordinates import CoordinateSummary
from app.schemas.detection import DetectionSummary
from app.schemas.football import ReadModel
from app.schemas.player_analytics import AnalyticsSummary
from app.schemas.reports import ReportSummary
from app.schemas.team_analytics import TacticsSummary
from app.schemas.team_assignment import ClassificationSummary
from app.schemas.tracking import TrackingSummary
from app.schemas.trajectories import TrajectorySummary


class MatchVideoRead(ReadModel):
    id: int
    match_id: int
    original_filename: str
    file_size_bytes: int
    mime_type: str
    container_format: str | None
    codec: str | None
    width: int
    height: int
    fps: float
    duration_seconds: float
    frame_count: int | None
    uploaded_by_user_id: int
    sha256: str | None
    warning_message: str | None
    created_at: datetime
    updated_at: datetime


class ProcessingJobRead(ReadModel):
    id: int
    match_id: int
    video_id: int
    job_type: JobType
    status: JobStatus
    progress_percent: int
    current_stage: str
    created_by_user_id: int
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    warning_message: str | None
    retry_count: int
    detection_summary: DetectionSummary | None
    tracking_summary: TrackingSummary | None
    classification_summary: ClassificationSummary | None
    coordinate_summary: CoordinateSummary | None
    trajectory_summary: TrajectorySummary | None
    analytics_summary: AnalyticsSummary | None
    tactics_summary: TacticsSummary | None
    report_summary: ReportSummary | None
    created_at: datetime
    updated_at: datetime
