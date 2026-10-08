from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.teams import TrackTeam
from app.schemas.football import ReadModel, RequestModel


class TeamOverride(RequestModel):
    # Explicit null clears the override. An omitted field is not a clear request.
    team: TrackTeam | None


class ClassificationProvenance(ReadModel):
    prototype_set_id: int | None = None
    sample_ids: list[str] = Field(default_factory=list)
    sample_count: int = Field(default=0, ge=0)
    accepted_sample_count: int = Field(default=0, ge=0)
    rejected_sample_count: int = Field(default=0, ge=0)
    margin: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    rejection_reason: str | None = None


class TeamAssignmentRead(ReadModel):
    match_id: int
    tracking_job_id: int
    track_id: int
    automatic_team: TrackTeam
    classification_mode: Literal["automatic", "user_seeded"] = "automatic"
    classification_provenance: ClassificationProvenance | None = None
    automatic_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    manual_team: TrackTeam | None
    effective_team: TrackTeam
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class ClassificationDiagnostics(ReadModel):
    diagnostic_basis: str = "automatic_track_aggregate"
    unknown_reasons: dict[str, int] = Field(default_factory=dict)
    budget_skipped_crops: int = Field(default=0, ge=0)
    attempted_crops: int = Field(ge=0)
    rejected_small_or_outside_crops: int = Field(ge=0)
    rejected_feature_crops: int = Field(ge=0)
    insufficient_sample_tracks: int = Field(ge=0)
    inconsistent_evidence_tracks: int = Field(ge=0)
    eligible_tracks: int = Field(ge=0)
    low_margin_tracks: int = Field(ge=0)
    median_sample_quality: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    median_samples_per_track: float | None = Field(ge=0, allow_inf_nan=False)
    cluster_separation_lab: float | None = Field(ge=0, allow_inf_nan=False)


class ClassificationSummary(ReadModel):
    tracking_job_id: int
    tracking_attempt: int
    processed_frames: int
    sampled_frames: int
    valid_samples: int
    total_tracks: int
    team_a_tracks: int
    team_b_tracks: int
    unknown_tracks: int
    sampling_method: str = "initial_candidates_v1"
    sample_interval: int
    max_samples_per_track: int
    min_samples: int
    min_crop_width: int
    min_crop_height: int
    unknown_threshold: float
    method: str = "median_lab_kmeans_v1"
    mapping: str = "ascending_lab_centroid"
    diagnostics: ClassificationDiagnostics | None = None
    classification_mode: Literal["automatic", "user_seeded"] = "automatic"
    prototype_set_id: int | None = None
