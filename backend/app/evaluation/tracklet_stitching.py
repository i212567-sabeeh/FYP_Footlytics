"""Conservative offline stitching experiment. Not enabled in production processing.

Only short, unambiguous motion-and-appearance continuations may join. Coordinates
must come from a valid fixed-camera calibration. The result is not player identity.
"""

from collections import Counter
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Observation:
    time: float
    position: tuple[float, float]  # Pitch metres, bbox bottom centre.
    size: tuple[float, float]  # Pixel width and height.


@dataclass(frozen=True)
class Tracklet:
    track_id: int
    observations: tuple[Observation, ...]
    color: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class StitchPolicy:
    max_gap_seconds: float = 0.6
    max_speed_mps: float = 10.0
    max_prediction_error_metres: float = 0.75
    max_scale_ratio: float = 1.25
    max_color_distance: float = 8.0
    competitor_distance_metres: float = 2.0


@dataclass(frozen=True)
class StitchDecision:
    source_tracklet: int
    destination_tracklet: int
    gap_seconds: float
    accepted: bool
    reason: str


def _velocity(a: Observation, b: Observation):
    return (np.asarray(b.position) - a.position) / (b.time - a.time)


def candidate_reason(source: Tracklet, dest: Tracklet, policy: StitchPolicy) -> str:
    a, b = source.observations[-1], dest.observations[0]
    gap = b.time - a.time
    if gap <= 0:
        return "temporal_overlap"
    if gap > policy.max_gap_seconds:
        return "excessive_gap"
    if len(source.observations) < 3 or len(dest.observations) < 3:
        return "insufficient_motion_evidence"
    distance = float(np.linalg.norm(np.asarray(b.position) - a.position))
    if distance / gap > policy.max_speed_mps:
        return "impossible_speed"
    ratios = np.asarray(a.size) / b.size
    if np.any(ratios > policy.max_scale_ratio) or np.any(
        ratios < 1 / policy.max_scale_ratio
    ):
        return "scale_mismatch"
    left = _velocity(source.observations[-3], a)
    right = _velocity(b, dest.observations[2])
    if max(np.linalg.norm(left), np.linalg.norm(right)) > policy.max_speed_mps:
        return "impossible_motion"
    if (
        max(
            np.linalg.norm(np.asarray(a.position) + left * gap - b.position),
            np.linalg.norm(np.asarray(b.position) - right * gap - a.position),
        )
        > policy.max_prediction_error_metres
    ):
        return "inconsistent_motion"
    if source.color is None or dest.color is None:
        return "insufficient_appearance_evidence"
    if (
        np.linalg.norm(np.asarray(source.color) - dest.color)
        > policy.max_color_distance
    ):
        return "appearance_mismatch"
    return "candidate"


def _near_competitor(source, dest, tracks, policy):
    for endpoint in (source.observations[-1], dest.observations[0]):
        for other in tracks:
            if other.track_id in (source.track_id, dest.track_id):
                continue
            # Inspect observed positions at the boundary, not extrapolated players.
            for observation in other.observations:
                if (
                    abs(observation.time - endpoint.time) <= 0.08
                    and np.linalg.norm(
                        np.asarray(observation.position) - endpoint.position
                    )
                    < policy.competitor_distance_metres
                ):
                    return True
    return False


def stitch_tracklets(
    tracks: list[Tracklet], policy: StitchPolicy | None = None
) -> tuple[dict[int, int], list[StitchDecision]]:
    policy = policy or StitchPolicy()
    if len({t.track_id for t in tracks}) != len(tracks):
        raise ValueError("Duplicate tracklet ID")
    for track in tracks:
        if track.track_id < 1 or not track.observations:
            raise ValueError("A tracklet needs a positive ID and real observations")
        previous = -1.0
        for obs in track.observations:
            if (
                not np.isfinite((obs.time, *obs.position, *obs.size)).all()
                or obs.time <= previous
                or min(obs.size) <= 0
            ):
                raise ValueError("Invalid ordered tracklet observation")
            previous = obs.time
    decisions = []
    for source in tracks:
        for dest in tracks:
            if (
                source.track_id == dest.track_id
                or dest.observations[0].time < source.observations[0].time
            ):
                continue
            reason = candidate_reason(source, dest, policy)
            if reason == "candidate" and _near_competitor(source, dest, tracks, policy):
                reason = "nearby_player_or_crossing"
            decisions.append(
                StitchDecision(
                    source.track_id,
                    dest.track_id,
                    dest.observations[0].time - source.observations[-1].time,
                    False,
                    reason,
                )
            )
    outgoing = Counter(d.source_tracklet for d in decisions if d.reason == "candidate")
    incoming = Counter(
        d.destination_tracklet for d in decisions if d.reason == "candidate"
    )
    canonical = {track.track_id: track.track_id for track in tracks}
    members = {t.track_id: [t] for t in tracks}
    result = []
    for decision in sorted(
        decisions,
        key=lambda d: (d.gap_seconds, d.source_tracklet, d.destination_tracklet),
    ):
        reason = decision.reason
        if reason == "candidate":
            if (
                outgoing[decision.source_tracklet] != 1
                or incoming[decision.destination_tracklet] != 1
            ):
                reason = "ambiguous_candidates"
            else:
                left, right = (
                    canonical[decision.source_tracklet],
                    canonical[decision.destination_tracklet],
                )
                overlap = any(
                    max(a.observations[0].time, b.observations[0].time)
                    <= min(a.observations[-1].time, b.observations[-1].time)
                    for a in members[left]
                    for b in members[right]
                )
                if overlap:
                    reason = "chain_overlap"
                else:
                    keep, drop = min(left, right), max(left, right)
                    members[keep] += members.pop(drop)
                    for track in members[keep]:
                        canonical[track.track_id] = keep
                    reason = "accepted_motion_scale_appearance_unique"
        result.append(
            StitchDecision(
                decision.source_tracklet,
                decision.destination_tracklet,
                decision.gap_seconds,
                reason.startswith("accepted_"),
                reason,
            )
        )
    return canonical, result
