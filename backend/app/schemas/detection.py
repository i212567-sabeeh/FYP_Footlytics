from datetime import datetime

from app.schemas.football import ReadModel


class DetectionSummary(ReadModel):
    processed_frames: int
    decoded_frames: int
    total_detections: int
    average_detections_per_processed_frame: float
    frame_stride: int
    frame_width: int
    frame_height: int
    timestamp_fallback_frames: int
    model: str
    device: str
    confidence_threshold: float
    inference_image_size: int
    roi_filter_applied: bool
    roi_skip_reason: str | None
    calibration_id: int
    calibration_updated_at: datetime
    artifact_format: str = "csv"
    # Boxes from candidate_confidence_threshold up to confidence_threshold are
    # stored only for ByteTrack's low-score association and never reported.
    # None marks earlier artifacts, which stored reported detections only.
    candidate_confidence_threshold: float | None = None
    low_confidence_detections: int = 0

    @property
    def stored_confidence_threshold(self) -> float:
        if self.candidate_confidence_threshold is None:
            return self.confidence_threshold
        return self.candidate_confidence_threshold

    @property
    def stored_detections(self) -> int:
        return self.total_detections + self.low_confidence_detections
