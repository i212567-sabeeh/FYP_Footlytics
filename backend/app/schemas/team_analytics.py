"""Descriptive visible-team geometry; nullable metrics mean unavailable."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.football import Identifier, ReadModel
from app.schemas.player_analytics import Count, Finite, Nonnegative, Positive

TacticalTeam = Literal["team_a", "team_b"]


class TeamSnapshot(ReadModel):
    frame_number: Count
    timestamp_seconds: Nonnegative
    team: TacticalTeam
    visible_players: Count
    sufficient_players: bool
    centroid_x: Finite | None = None
    centroid_y: Finite | None = None
    width_metres: Nonnegative | None = None
    depth_metres: Nonnegative | None = None
    compactness_radius_metres: Nonnegative | None = None
    mean_pairwise_distance_metres: Nonnegative | None = None
    convex_hull_area_m2: Nonnegative | None = None
    bounding_box_area_m2: Nonnegative | None = None
    centroid_distance_to_opponent_metres: Nonnegative | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        required = (
            self.centroid_x,
            self.centroid_y,
            self.width_metres,
            self.depth_metres,
            self.compactness_radius_metres,
            self.mean_pairwise_distance_metres,
            self.bounding_box_area_m2,
        )
        if self.sufficient_players:
            if self.visible_players < 2 or any(v is None for v in required):
                raise ValueError("Sufficient snapshots require geometry")
        elif any(
            v is not None
            for v in (
                *required,
                self.convex_hull_area_m2,
                self.centroid_distance_to_opponent_metres,
            )
        ):
            raise ValueError("Insufficient snapshots have unavailable geometry")
        return self


class TeamTacticalSummary(ReadModel):
    team: TacticalTeam
    valid_snapshots: Count
    insufficient_snapshots: Count
    avg_visible_players: Nonnegative | None
    avg_centroid_x: Finite | None
    avg_centroid_y: Finite | None
    avg_width_metres: Nonnegative | None
    avg_depth_metres: Nonnegative | None
    avg_compactness_radius_metres: Nonnegative | None
    avg_pairwise_distance_metres: Nonnegative | None
    hull_snapshots: Count
    avg_convex_hull_area_m2: Nonnegative | None
    avg_bounding_box_area_m2: Nonnegative | None
    both_teams_valid_snapshots: Count
    avg_centroid_distance_to_opponent_metres: Nonnegative | None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        required = (
            self.avg_visible_players,
            self.avg_centroid_x,
            self.avg_centroid_y,
            self.avg_width_metres,
            self.avg_depth_metres,
            self.avg_compactness_radius_metres,
            self.avg_pairwise_distance_metres,
            self.avg_bounding_box_area_m2,
        )
        if any((v is not None) != bool(self.valid_snapshots) for v in required):
            raise ValueError("Only valid snapshots have aggregate geometry")
        for count, value in (
            (self.hull_snapshots, self.avg_convex_hull_area_m2),
            (
                self.both_teams_valid_snapshots,
                self.avg_centroid_distance_to_opponent_metres,
            ),
        ):
            if count > self.valid_snapshots or bool(count) != (value is not None):
                raise ValueError("Inconsistent optional metric coverage")
        return self


class TacticsSummary(ReadModel):
    source_rows: Count
    usable_rows: Count
    rejected_rows: Count
    assigned_rows: Count
    unknown_rows: Count
    observed_frames: Count
    trajectory_job_id: Identifier
    trajectory_attempt: Count
    pitch_length_metres: Positive
    pitch_width_metres: Positive
    min_players_per_team: Annotated[int, Field(ge=2, le=22)]
    aggregation: Literal["per_valid_snapshot"] = "per_valid_snapshot"
    snapshot_method: Literal["usable_positions_by_frame"] = "usable_positions_by_frame"
    artifact_format: Literal["csv_bundle"] = "csv_bundle"

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.source_rows != self.usable_rows + self.rejected_rows
            or self.usable_rows != self.assigned_rows + self.unknown_rows
            or self.observed_frames > self.usable_rows
            or self.pitch_width_metres > self.pitch_length_metres
        ):
            raise ValueError("Inconsistent tactical provenance")
        return self


class TeamAnalyticsRead(ReadModel):
    match_id: int
    video_id: int
    job_id: int
    summary: TacticsSummary
    teams: list[TeamTacticalSummary]
