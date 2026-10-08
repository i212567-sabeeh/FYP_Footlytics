"""Small current-result summaries; artifact rows and storage paths stay private."""

from datetime import datetime

from pydantic import Field

from app.core.jobs import JobStatus
from app.schemas.football import ReadModel


class ReviewSummary(ReadModel):
    job_id: int
    job_updated_at: datetime
    status: JobStatus
    video_id: int
    processed_frames: int
    frame_stride: int
    # Sampling bounds include empty frames, rather than only visible observations.
    first_frame: int = Field(
        description="First processed frame, including empty frames"
    )
    last_frame: int = Field(description="Last processed frame, including empty frames")
    frame_width: int
    frame_height: int


class DetectionReviewSummary(ReviewSummary):
    total_detections: int
    average_detections_per_processed_frame: float


class TrackingReviewSummary(ReviewSummary):
    unique_tracks: int
    tracked_rows: int
    average_visible_tracks_per_frame: float
