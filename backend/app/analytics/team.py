"""Instantaneous visible-team geometry. No motion or tactical quality is inferred."""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from itertools import combinations, groupby

from pydantic import BaseModel

from app.analytics.trajectory_rows import AnalyticsError, CleanObservation
from app.schemas.team_analytics import TacticalTeam, TeamSnapshot, TeamTacticalSummary

TEAMS = ("team_a", "team_b")
AVERAGES = {
    "visible_players": "avg_visible_players",
    "centroid_x": "avg_centroid_x",
    "centroid_y": "avg_centroid_y",
    "width_metres": "avg_width_metres",
    "depth_metres": "avg_depth_metres",
    "compactness_radius_metres": "avg_compactness_radius_metres",
    "mean_pairwise_distance_metres": "avg_pairwise_distance_metres",
    "convex_hull_area_m2": "avg_convex_hull_area_m2",
    "bounding_box_area_m2": "avg_bounding_box_area_m2",
    "centroid_distance_to_opponent_metres": "avg_centroid_distance_to_opponent_metres",
}


def snapshot(
    frame: int,
    timestamp: float,
    team: TacticalTeam,
    positions: list[tuple[float, float]],
    minimum: int,
) -> TeamSnapshot:
    if minimum < 2 or any(not all(math.isfinite(v) for v in p) for p in positions):
        raise AnalyticsError("Invalid team snapshot positions or visibility threshold.")
    n = len(positions)
    base = dict(
        frame_number=frame,
        timestamp_seconds=timestamp,
        team=team,
        visible_players=n,
        sufficient_players=n >= minimum,
    )
    if n < minimum:
        return TeamSnapshot(**base)
    centroid = tuple(math.fsum(p[i] for p in positions) / n for i in (0, 1))
    depth = max(p[0] for p in positions) - min(p[0] for p in positions)
    width = max(p[1] for p in positions) - min(p[1] for p in positions)
    hull_area = None
    if n >= 3:
        import cv2
        import numpy as np

        area = cv2.contourArea(cv2.convexHull(np.asarray(positions, dtype=np.float32)))
        hull_area = area if area > 0 else None
    return TeamSnapshot(
        **base,
        centroid_x=centroid[0],
        centroid_y=centroid[1],
        width_metres=width,
        depth_metres=depth,
        compactness_radius_metres=math.fsum(math.dist(p, centroid) for p in positions)
        / n,
        mean_pairwise_distance_metres=math.fsum(
            math.dist(a, b) for a, b in combinations(positions, 2)
        )
        / (n * (n - 1) / 2),
        convex_hull_area_m2=hull_area,
        bounding_box_area_m2=width * depth,
    )


@dataclass
class Aggregate:
    valid: int = 0
    insufficient: int = 0
    means: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, row: TeamSnapshot) -> None:
        if not row.sufficient_players:
            self.insufficient += 1
            return
        self.valid += 1
        for key in AVERAGES:
            value = getattr(row, key)
            if value is not None:
                count = self.counts.get(key, 0) + 1
                mean = self.means.get(key, 0.0)
                self.means[key] = mean + (value - mean) / count
                self.counts[key] = count

    def summary(self, team: TacticalTeam) -> TeamTacticalSummary:
        return TeamTacticalSummary(
            team=team,
            valid_snapshots=self.valid,
            insufficient_snapshots=self.insufficient,
            hull_snapshots=self.counts.get("convex_hull_area_m2", 0),
            both_teams_valid_snapshots=self.counts.get(
                "centroid_distance_to_opponent_metres", 0
            ),
            **{name: self.means.get(key) for key, name in AVERAGES.items()},
        )


@dataclass
class TacticsRun:
    observed_frames: int
    assigned_rows: int
    unknown_rows: int
    teams: list[TeamTacticalSummary]


def calculate_teams(
    rows: Iterable[CleanObservation],
    assignments: dict[int, str],
    minimum: int,
    total: int,
    *,
    write: Callable[[str, BaseModel], None],
    progress: Callable[[int, int], None],
) -> TacticsRun:
    aggregates = {team: Aggregate() for team in TEAMS}
    processed = assigned = unknown = frames = 0
    previous_frame = -1
    previous_timestamp = -1.0
    for frame, group in groupby(rows, key=lambda row: row.frame):
        positions = {team: [] for team in TEAMS}
        seen = set()
        timestamp = None
        for row in group:
            if row.clean is None:
                continue
            if row.track_id in seen or (
                timestamp is not None and timestamp != row.timestamp
            ):
                raise AnalyticsError(
                    "Cleaned trajectories contain duplicate tracks "
                    "or inconsistent frame timestamps."
                )
            timestamp = row.timestamp
            seen.add(row.track_id)
            team = assignments.get(row.track_id)
            if team in positions:
                positions[team].append(row.clean)
                assigned += 1
            else:
                unknown += 1
            processed += 1
        if timestamp is None:
            continue
        if frame <= previous_frame or timestamp < previous_timestamp:
            raise AnalyticsError(
                "Cleaned frame snapshots are not ordered consistently."
            )
        previous_frame, previous_timestamp = frame, timestamp
        snapshots = [
            snapshot(frame, timestamp, team, positions[team], minimum) for team in TEAMS
        ]
        if all(row.sufficient_players for row in snapshots):
            a, b = snapshots
            distance = math.dist(
                (a.centroid_x, a.centroid_y), (b.centroid_x, b.centroid_y)
            )
            for row in snapshots:
                row.centroid_distance_to_opponent_metres = distance
        for row in snapshots:
            write("team_tactics_frames", row)
            aggregates[row.team].add(row)
        frames += 1
        progress(processed, total)
    summaries = [aggregates[team].summary(team) for team in TEAMS]
    for summary in summaries:
        write("team_tactics_summary", summary)
    return TacticsRun(frames, assigned, unknown, summaries)
