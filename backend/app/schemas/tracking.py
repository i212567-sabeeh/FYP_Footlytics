from app.schemas.football import ReadModel


class TrackingSummary(ReadModel):
    processed_frames: int
    total_detections: int
    total_track_rows: int
    unique_tracks: int
    frame_stride: int
    frame_width: int
    frame_height: int
    detection_job_id: int
    detection_attempt: int
    tracker: str = "bytetrack"
    track_high_thresh: float
    track_low_thresh: float
    track_match_thresh: float
    track_buffer: int
    artifact_format: str = "csv"
    # Later additions have defaults so earlier tracking jobs remain valid.
    track_buffer_updates: int | None = None
    track_buffer_seconds: float | None = None
    low_confidence_detections: int = 0
    low_confidence_association: bool | None = None
