"""Validated settings shared by the API and background workers."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FOOTLYTICS"
    report_heatmap_limit: int = Field(default=4, ge=0, le=12)
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    database_url: str = "sqlite:///./storage/footlytics.db"
    storage_dir: Path = PROJECT_ROOT / "storage"

    jwt_secret: SecretStr | None = None
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)

    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "video-processing"
    redis_connect_timeout_seconds: float = Field(default=2, gt=0, le=30)
    rq_job_timeout_seconds: int = Field(default=120, ge=30)
    rq_result_ttl_seconds: int = Field(default=86400, ge=60)
    ffprobe_path: str = "ffprobe"
    video_inspection_timeout_seconds: float = Field(default=30, gt=0, le=120)
    yolo_model: str = "yolo11n.pt"
    yolo_confidence: float = Field(default=0.25, gt=0, le=1, allow_inf_nan=False)
    yolo_image_size: int = Field(default=640, ge=32, le=4096, multiple_of=32)
    detection_frame_stride: int = Field(default=1, ge=1, le=10000)
    detection_roi_enabled: bool = True
    detection_job_timeout_seconds: int = Field(default=21600, ge=60)
    track_high_thresh: float = Field(default=0.25, gt=0, le=1, allow_inf_nan=False)
    # Also the detector's inference floor, so zero would store every candidate.
    track_low_thresh: float = Field(default=0.1, gt=0, lt=1, allow_inf_nan=False)
    track_match_thresh: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)
    track_buffer: int = Field(default=30, ge=1, le=10000)
    team_sample_interval: int = Field(default=15, ge=1, le=10000)
    team_max_samples_per_track: int = Field(default=20, ge=3, le=200)
    team_min_samples: int = Field(default=3, ge=2, le=200)
    team_min_crop_width: int = Field(default=8, ge=1, le=512)
    team_min_crop_height: int = Field(default=8, ge=1, le=512)
    team_unknown_threshold: float = Field(default=0.6, gt=0, le=1, allow_inf_nan=False)
    trajectory_max_plausible_speed_mps: float = Field(
        default=12, gt=0, le=100, allow_inf_nan=False
    )
    trajectory_max_gap_seconds: float = Field(
        default=2, gt=0, le=60, allow_inf_nan=False
    )
    trajectory_smoothing_window: int = Field(default=3, ge=1, le=11)
    trajectory_smoothing_max_shift_metres: float = Field(
        default=0.5, ge=0, le=5, allow_inf_nan=False
    )
    player_sprint_speed_threshold_mps: float = Field(
        default=7, gt=0, le=100, allow_inf_nan=False
    )
    player_sprint_min_duration_seconds: float = Field(
        default=1, gt=0, le=60, allow_inf_nan=False
    )
    # Minimum elapsed time of one movement measurement. Displacements over a
    # single 25 FPS frame are dominated by bounding-box jitter (docs/
    # KPI_QUALITY_REPORT.md); 0 measures every consecutive observation pair.
    player_speed_window_seconds: float = Field(
        default=0.2, ge=0, le=2, allow_inf_nan=False
    )
    player_heatmap_bins_x: int = Field(default=20, ge=1, le=100)
    player_heatmap_bins_y: int = Field(default=12, ge=1, le=100)
    tactics_min_players_per_team: int = Field(default=3, ge=2, le=22)
    device: str = "auto"
    max_upload_size: int = Field(default=2 * 1024**3, gt=0)
    default_processing_profile: str = "balanced"

    @model_validator(mode="after")
    def validate_tracking_thresholds(self) -> "Settings":
        if self.track_low_thresh >= self.track_high_thresh:
            raise ValueError("TRACK_LOW_THRESH must be less than TRACK_HIGH_THRESH")
        # ByteTrack starts tracks at TRACK_HIGH_THRESH. Keeping it at or above
        # YOLO_CONFIDENCE means every track begins from a reported detection;
        # lower stored candidates can only extend existing tracks.
        if self.track_high_thresh < self.yolo_confidence:
            raise ValueError("TRACK_HIGH_THRESH must be at least YOLO_CONFIDENCE")
        if self.team_min_samples > self.team_max_samples_per_track:
            raise ValueError(
                "TEAM_MIN_SAMPLES must not exceed TEAM_MAX_SAMPLES_PER_TRACK"
            )
        return self

    @property
    def detection_candidate_confidence(self) -> float:
        """Inference floor covering ByteTrack's low-score band.

        Boxes from here up to YOLO_CONFIDENCE are stored only as tracking
        candidates; detection counts and overlays still use YOLO_CONFIDENCE.
        """
        return min(self.yolo_confidence, self.track_low_thresh)

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"auto", "cpu", "cuda"} and not re.fullmatch(
            r"cuda:\d+", value
        ):
            raise ValueError("DEVICE must be auto, cpu, cuda or cuda:<index>")
        return value

    @field_validator("trajectory_smoothing_window")
    @classmethod
    def validate_trajectory_window(cls, value: int) -> int:
        if value % 2 != 1:
            raise ValueError("TRAJECTORY_SMOOTHING_WINDOW must be odd")
        return value

    @field_validator("yolo_model")
    @classmethod
    def validate_yolo_model(cls, value: str) -> str:
        value = value.strip()
        if not value or "://" in value or Path(value).suffix.lower() != ".pt":
            raise ValueError(
                "YOLO_MODEL must name pretrained .pt weights or a local .pt file"
            )
        return value

    def require_jwt_secret(self) -> str:
        """Fail closed at server startup without blocking database-only commands."""
        secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
        if (
            len(secret.encode("utf-8")) < 32
            or secret.startswith("replace-with-")
            or len(set(secret)) < 8
        ):
            raise ValueError(
                "Set JWT_SECRET to a random secret of at least 32 bytes in .env."
            )
        return secret

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_PREFIX must start with / and have no trailing /")
        return value

    @field_validator("storage_dir")
    @classmethod
    def resolve_storage_dir(cls, value: Path) -> Path:
        return (PROJECT_ROOT / value).resolve()

    @field_validator("database_url")
    @classmethod
    def resolve_database_url(cls, value: str) -> str:
        url = make_url(value)
        if url.get_backend_name() == "sqlite" and url.database not in (
            None,
            "",
            ":memory:",
        ):
            # CLI commands and servers must locate the same database from any cwd.
            database_path = (PROJECT_ROOT / url.database).resolve()
            url = url.set(database=database_path.as_posix())
            return url.render_as_string(hide_password=False)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
