"""Finite, track-scoped movement metrics. No player identity is inferred."""

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.football import Identifier, ReadModel

Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0)]


class TrackAnalytics(ReadModel):
    track_id: Identifier
    # Extents of usable observations, not a claim of continuous observed time.
    first_frame: Count | None
    last_frame: Count | None
    first_timestamp: Nonnegative | None
    last_timestamp: Nonnegative | None
    segment_count: Count
    usable_observation_count: Count
    valid_interval_count: Count
    excluded_interval_count: Count
    active_duration_seconds: Nonnegative
    total_distance_metres: Nonnegative
    average_speed_mps: Nonnegative | None
    average_speed_kmh: Nonnegative | None
    max_speed_mps: Nonnegative | None
    max_speed_kmh: Nonnegative | None
    sprint_count: Count
    sprint_distance_metres: Nonnegative
    sprint_duration_seconds: Nonnegative

    @model_validator(mode="after")
    def consistent(self) -> Self:
        extents = (
            self.first_frame,
            self.last_frame,
            self.first_timestamp,
            self.last_timestamp,
        )
        if self.usable_observation_count:
            if (
                any(v is None for v in extents)
                or self.first_frame > self.last_frame
                or self.first_timestamp > self.last_timestamp
            ):
                raise ValueError("Invalid observation extents")
        elif any(v is not None for v in extents):
            raise ValueError("Empty tracks have no observation extents")
        if self.segment_count > self.usable_observation_count or bool(
            self.segment_count
        ) != bool(self.usable_observation_count):
            raise ValueError("Invalid segment count")
        speeds = (
            self.average_speed_mps,
            self.average_speed_kmh,
            self.max_speed_mps,
            self.max_speed_kmh,
        )
        if self.active_duration_seconds:
            if not self.valid_interval_count or any(v is None for v in speeds):
                raise ValueError("Valid intervals require speed metrics")
            if (
                not math.isclose(
                    self.average_speed_mps,
                    self.total_distance_metres / self.active_duration_seconds,
                )
                or self.average_speed_mps > self.max_speed_mps + 1e-9
            ):
                raise ValueError("Inconsistent speed metrics")
            if not math.isclose(
                self.average_speed_kmh, self.average_speed_mps * 3.6
            ) or not math.isclose(self.max_speed_kmh, self.max_speed_mps * 3.6):
                raise ValueError("Inconsistent speed units")
        elif (
            self.valid_interval_count
            or self.total_distance_metres
            or any(v is not None for v in speeds)
        ):
            raise ValueError(
                "No valid duration means unavailable speeds and zero distance"
            )
        if (
            self.sprint_duration_seconds > self.active_duration_seconds + 1e-9
            or self.sprint_distance_metres > self.total_distance_metres + 1e-9
            or bool(self.sprint_count) != bool(self.sprint_duration_seconds)
        ):
            raise ValueError("Inconsistent sprint metrics")
        return self


class MovementInterval(ReadModel):
    track_id: Identifier
    segment_id: Identifier
    start_frame: Count
    end_frame: Count
    start_timestamp: Nonnegative
    end_timestamp: Nonnegative
    start_x: Finite
    start_y: Finite
    end_x: Finite
    end_y: Finite
    dt_seconds: Positive
    distance_metres: Nonnegative
    speed_mps: Nonnegative
    speed_kmh: Nonnegative
    # A threshold crossing alone is not a duration-qualified sprint event.
    above_sprint_threshold: bool


class SprintEvent(ReadModel):
    track_id: Identifier
    segment_id: Identifier
    start_frame: Count
    end_frame: Count
    start_timestamp: Nonnegative
    end_timestamp: Nonnegative
    duration_seconds: Positive
    distance_metres: Nonnegative
    max_speed_mps: Nonnegative


class HeatmapCell(ReadModel):
    track_id: Identifier
    x_bin: Count
    y_bin: Count
    x_min: Nonnegative
    x_max: Positive
    y_min: Nonnegative
    y_max: Positive
    occupancy_seconds: Positive
    occupancy_fraction: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]


class AnalyticsSummary(ReadModel):
    source_rows: Count
    usable_rows: Count
    rejected_rows: Count
    unique_tracks: Count
    valid_intervals: Count
    excluded_intervals: Count
    sprint_events: Count
    heatmap_cells: Count
    trajectory_job_id: Identifier
    trajectory_attempt: Count
    pitch_length_metres: Positive
    pitch_width_metres: Positive
    sprint_speed_threshold_mps: Positive
    sprint_min_duration_seconds: Positive
    max_plausible_speed_mps: Positive
    max_gap_seconds: Positive
    heatmap_bins_x: Annotated[int, Field(ge=1, le=100)]
    heatmap_bins_y: Annotated[int, Field(ge=1, le=100)]
    # Results saved before this field existed measured every consecutive pair.
    speed_window_seconds: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 0
    method: Literal["consecutive_clean_intervals_v1", "minimum_time_windows_v2"] = (
        "consecutive_clean_intervals_v1"
    )
    continuity_policy: Literal["rejected_observation_breaks"] = (
        "rejected_observation_breaks"
    )
    heatmap_method: Literal["interval_start_time_weighted"] = (
        "interval_start_time_weighted"
    )
    artifact_format: Literal["csv_bundle"] = "csv_bundle"

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.source_rows != self.usable_rows + self.rejected_rows
            or self.unique_tracks > self.source_rows
            or self.valid_intervals > self.usable_rows
            or self.sprint_events > self.valid_intervals
            or self.heatmap_cells
            > self.unique_tracks * self.heatmap_bins_x * self.heatmap_bins_y
            or self.pitch_width_metres > self.pitch_length_metres
        ):
            raise ValueError("Inconsistent analytics summary")
        return self


class ObservationCoverage(ReadModel):
    video_duration_seconds: Positive | None = None
    observed_coverage_percent: (
        Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] | None
    ) = None
    coverage_warning: str | None = None


class TrackAnalyticsRead(TrackAnalytics, ObservationCoverage):
    match_id: int
    video_id: int
    job_id: int
    trajectory_job_id: int
    # The saved result's movement window (0: every consecutive observation pair).
    speed_window_seconds: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 0


class TrackHeatmapRead(ObservationCoverage):
    match_id: int
    video_id: int
    job_id: int
    trajectory_job_id: int
    track_id: Identifier
    pitch_length_metres: Positive
    pitch_width_metres: Positive
    bins_x: int
    bins_y: int
    method: Literal["interval_start_time_weighted"] = "interval_start_time_weighted"
    total_occupancy_seconds: Nonnegative
    # Sparse occupied cells; omitted cells have zero occupancy.
    cells: list[HeatmapCell]
