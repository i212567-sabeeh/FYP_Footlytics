"""Explicit validation manifests, independent labels and saved prediction provenance."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FileRef(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Clip(StrictModel):
    clip_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    video: FileRef
    frames: FileRef
    annotations: FileRef
    fps: float = Field(gt=0)
    frame_count: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    football_format: Literal["11v11", "5v5"]
    conditions: str = Field(min_length=1)
    pitch_length_metres: float | None = Field(default=None, gt=0)
    pitch_width_metres: float | None = Field(default=None, gt=0)
    landmarks: FileRef | None = None
    calibration_frame_number: int | None = Field(default=None, ge=0)
    independent_pitch_ground_truth: bool = False
    pitch_ground_truth_method: str | None = None
    team_mapping: dict[str, str] | None = None
    team_mapping_basis: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.clip_id == "OVERALL":
            raise ValueError("OVERALL is reserved for aggregate results")
        if (self.pitch_length_metres is None) != (self.pitch_width_metres is None):
            raise ValueError("Supply both Match pitch dimensions or neither")
        if self.landmarks and (
            self.pitch_length_metres is None
            or self.calibration_frame_number is None
            or self.calibration_frame_number >= self.frame_count
        ):
            raise ValueError(
                "Landmarks require pitch dimensions and a calibration frame"
            )
        if self.independent_pitch_ground_truth and not self.pitch_ground_truth_method:
            raise ValueError(
                "Describe the independent player pitch ground-truth method"
            )
        if self.team_mapping is not None:
            teams = {"team_a", "team_b"}
            if (
                set(self.team_mapping) != teams
                or set(self.team_mapping.values()) != teams
            ):
                raise ValueError(
                    "Team mapping must be a bijection of Team A and Team B"
                )
            if not self.team_mapping_basis:
                raise ValueError("Document team-color mapping independently of scores")
        return self


class Dataset(StrictModel):
    schema_version: Literal[1] = 1
    description: str = Field(min_length=1)
    provenance: Literal["human", "synthetic"]
    annotation_author: str = Field(min_length=1)
    annotation_notes: str = Field(min_length=1)
    independent_ground_truth: bool
    clips: list[Clip] = Field(max_length=20)

    @model_validator(mode="after")
    def distinct(self):
        if len({clip.clip_id for clip in self.clips}) != len(self.clips):
            raise ValueError("Duplicate clip ID")
        if len({clip.video.sha256 for clip in self.clips}) != len(self.clips):
            raise ValueError("Duplicate video content would double-count the dataset")
        if (
            self.clips
            and self.provenance == "human"
            and not self.independent_ground_truth
        ):
            raise ValueError("Real evaluation requires independent human ground truth")
        return self


class RuntimeMeasurement(StrictModel):
    stage: Literal["detection", "tracking", "team_classification", "coordinate_mapping"]
    seconds: float = Field(gt=0)
    frames: int = Field(gt=0)
    device: str = Field(min_length=1)
    setup_included: bool
    hardware: str = Field(min_length=1)
    measurement_method: str = Field(min_length=1)


class CalibrationSnapshot(StrictModel):
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame_number: int = Field(ge=0)
    pitch_length_metres: float = Field(gt=0)
    pitch_width_metres: float = Field(gt=0)
    matrix: list[list[float]]


class PredictionClip(StrictModel):
    clip_id: str
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pipeline_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    processed_frames: list[int] = Field(max_length=10000)
    detections: FileRef | None = None
    tracks: FileRef | None = None
    automatic_teams: FileRef | None = None
    coordinates: FileRef | None = None
    calibration: FileRef | None = None
    cleaned: FileRef | None = None
    runtime: list[RuntimeMeasurement] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_frames(self):
        if self.processed_frames != sorted(set(self.processed_frames)):
            raise ValueError("Processed frames must be unique and sorted")
        if len({item.stage for item in self.runtime}) != len(self.runtime):
            raise ValueError("Duplicate runtime stage")
        if self.coordinates and self.calibration is None:
            raise ValueError("Coordinate artifacts require their saved calibration")
        if any(item.frames > len(self.processed_frames) for item in self.runtime):
            raise ValueError("Timed frames cannot exceed declared processed frames")
        return self


class Predictions(StrictModel):
    schema_version: Literal[1] = 1
    source: Literal["footlytics", "synthetic"]
    generated_at: datetime
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pipeline_config: dict
    software_versions: dict[str, str] = Field(min_length=1)
    model_weights: FileRef | None = None
    source_revision: str = Field(min_length=1)
    clips: list[PredictionClip] = Field(max_length=20)

    @model_validator(mode="after")
    def weights_and_time(self):
        if self.generated_at.tzinfo is None:
            raise ValueError("Prediction generation time must include a timezone")
        if any(clip.detections for clip in self.clips) and self.model_weights is None:
            raise ValueError(
                "Detection provenance requires the exact weights file/hash"
            )
        return self


class EvaluationConfig(StrictModel):
    detection_iou: float = Field(default=0.5, gt=0, le=1)
    tracking_iou: float = Field(default=0.5, gt=0, le=1)
    association_iou: float = Field(default=0.5, gt=0, le=1)
    p95_min_observations: int = Field(default=20, ge=20)
    max_rows_per_file: int = Field(default=200000, ge=1, le=1000000)


@dataclass(frozen=True)
class Frame:
    number: int
    timestamp: float
    tracking_evaluable: bool


@dataclass(frozen=True)
class Observation:
    frame: int
    timestamp: float
    box: tuple[float, float, float, float]
    track_id: str | None = None
    team: str | None = None
    ignored: bool = False
    confidence: float | None = None
    pitch: tuple[float, float] | None = None


@dataclass(frozen=True)
class Landmark:
    identifier: str
    image: tuple[float, float]
    pitch: tuple[float, float]
    role: str


@dataclass
class ClipData:
    clip: Clip
    frames: list[Frame]
    annotations: list[Observation]
    landmarks: list[Landmark] = field(default_factory=list)
    detections: list[Observation] | None = None
    tracks: list[Observation] | None = None
    automatic_teams: dict[str, str] | None = None
    coordinates: list[Observation] | None = None
    cleaned_rows: int | None = None
    usable_cleaned_rows: int | None = None
    prediction: PredictionClip | None = None


class InputError(ValueError):
    def __init__(self, message: str, *, issues: list[dict] | None = None):
        super().__init__(message)
        self.issues = issues or []
