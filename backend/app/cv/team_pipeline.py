"""Stream existing tracking CSVs; decode only selected frames, once per frame."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.cv.team_classifier import (
    Appearance,
    Image,
    TeamPrediction,
    classify_tracks,
    jersey_bounds,
    jersey_crop,
    jersey_feature,
)
from app.cv.team_colors import classify_seeded
from app.cv.tracking_rows import TrackingRowsError, tracking_rows
from app.schemas.detection import DetectionSummary
from app.schemas.tracking import TrackingSummary


class ClassificationError(Exception):
    """Only curated, path-free messages may cross the worker/API boundary."""


@dataclass
class TrackEvidence:
    samples: list[Appearance] = field(default_factory=list)
    attempts: int = 0
    last_frame: int | None = None
    valid_candidates: int = 0


@dataclass(frozen=True)
class ClassificationRun:
    predictions: list[TeamPrediction]
    processed_frames: int
    sampled_frames: int
    valid_samples: int
    diagnostics: dict = field(default_factory=dict)


def _sample_schedule(
    path: Path,
    detection: DetectionSummary,
    tracking: TrackingSummary,
    duration: float,
    settings: Settings,
) -> dict[int, set[int]]:
    """Two streaming passes, O(tracks * sample cap) memory; no image history.

    Invalid/tiny torso boxes cannot exhaust a track's sample budget. Select valid
    candidate indices across its whole lifetime rather than only its first seconds.
    """
    counts: dict[int, int] = {}
    previous: dict[int, int] = {}
    row_count = 0
    rows = tracking_rows(path, detection, duration)
    try:
        for row in rows:
            row_count += 1
            counts.setdefault(row.track_id, 0)
            if (
                row_count > tracking.total_track_rows
                or len(counts) > tracking.unique_tracks
            ):
                raise ClassificationError(
                    "The tracking CSV row or track count changed."
                )
            if (
                row.track_id in previous
                and row.frame - previous[row.track_id] < settings.team_sample_interval
            ):
                continue
            previous[row.track_id] = row.frame
            if (
                jersey_bounds(
                    detection.frame_width, detection.frame_height, row.box, settings
                )
                is not None
            ):
                counts[row.track_id] += 1
    except TrackingRowsError as error:
        raise ClassificationError(str(error)) from error
    finally:
        rows.close()
    if row_count != tracking.total_track_rows or len(counts) != tracking.unique_tracks:
        raise ClassificationError(
            "The tracking CSV is incomplete or its summary changed."
        )
    schedule = {}
    for track_id, count in counts.items():
        size = min(count, settings.team_max_samples_per_track)
        schedule[track_id] = (
            {round(i * (count - 1) / (size - 1)) for i in range(size)}
            if size > 1
            else {0}
            if size
            else set()
        )
    return schedule


def classify_tracking(
    path: Path,
    detection: DetectionSummary,
    tracking: TrackingSummary,
    duration: float,
    settings: Settings,
    *,
    load_frame: Callable[[int], Image],
    progress: Callable[[int, int], None],
    prototypes: dict[TrackTeam, Appearance] | None = None,
) -> ClassificationRun:
    schedule = _sample_schedule(path, detection, tracking, duration, settings)
    evidence: dict[int, TrackEvidence] = {}
    sampled_frames = valid_samples = row_count = processed = 0
    diagnostics = {
        "diagnostic_basis": "automatic_track_aggregate",
        "attempted_crops": 0,
        "budget_skipped_crops": 0,
        "rejected_small_or_outside_crops": 0,
        "rejected_feature_crops": 0,
    }
    rows = tracking_rows(path, detection, duration)
    try:
        row = next(rows, None)
        for number in range(0, detection.decoded_frames, detection.frame_stride):
            image = None
            while row is not None and row.frame == number:
                row_count += 1
                if row_count > tracking.total_track_rows:
                    raise ClassificationError("The tracking CSV row count changed.")
                track = evidence.setdefault(row.track_id, TrackEvidence())
                if len(evidence) > tracking.unique_tracks:
                    raise ClassificationError("The tracking CSV track count changed.")
                due = (
                    track.last_frame is None
                    or number - track.last_frame >= settings.team_sample_interval
                )
                if due:
                    track.last_frame = number
                    track.attempts += 1
                    diagnostics["attempted_crops"] += 1
                    bounds = jersey_bounds(
                        detection.frame_width, detection.frame_height, row.box, settings
                    )
                    if bounds is None:
                        diagnostics["rejected_small_or_outside_crops"] += 1
                    if bounds is not None:
                        selected = track.valid_candidates in schedule[row.track_id]
                        track.valid_candidates += 1
                        if not selected:
                            diagnostics["budget_skipped_crops"] += 1
                            row = next(rows, None)
                            continue
                        if image is None:
                            image = load_frame(number)
                            if image is None or image.shape != (
                                detection.frame_height,
                                detection.frame_width,
                                3,
                            ):
                                raise ClassificationError(
                                    "Decoded frame dimensions do not match tracking."
                                )
                            sampled_frames += 1
                        crop = jersey_crop(image, row.box, settings)
                        if crop is not None:
                            feature = jersey_feature(crop)
                            if feature is not None:
                                track.samples.append(feature)
                                valid_samples += 1
                            else:
                                diagnostics["rejected_feature_crops"] += 1
                        else:
                            diagnostics["rejected_feature_crops"] += 1
                row = next(rows, None)
            # Only compact features survive the frame iteration.
            del image
            processed += 1
            progress(processed, detection.processed_frames)
        if (
            row is not None
            or row_count != tracking.total_track_rows
            or len(evidence) != tracking.unique_tracks
        ):
            raise ClassificationError(
                "The tracking CSV is incomplete or its summary changed."
            )
    except TrackingRowsError as error:
        raise ClassificationError(str(error)) from error
    finally:
        rows.close()
    samples = {key: value.samples for key, value in evidence.items()}
    predictions = classify_tracks(samples, settings, diagnostics=diagnostics)
    if prototypes is not None:
        predictions = classify_seeded(samples, prototypes, settings)
        diagnostics.update(
            {
                "diagnostic_basis": "user_seeded_consensus",
                "cluster_separation_lab": float(
                    np.linalg.norm(
                        np.asarray(prototypes[TrackTeam.TEAM_A].color)
                        - prototypes[TrackTeam.TEAM_B].color
                    )
                ),
                "insufficient_sample_tracks": sum(
                    p.rejection_reason == "insufficient_consistent_samples"
                    for p in predictions
                ),
                "inconsistent_evidence_tracks": sum(
                    p.rejection_reason == "conflicting_team_evidence"
                    for p in predictions
                ),
                "eligible_tracks": sum(p.confidence > 0 for p in predictions),
                "low_margin_tracks": sum(
                    p.rejection_reason == "inconsistent_color_evidence"
                    for p in predictions
                ),
            }
        )
    diagnostics["unknown_reasons"] = dict(
        Counter(p.rejection_reason for p in predictions if p.rejection_reason)
    )
    return ClassificationRun(
        predictions, processed, sampled_frames, valid_samples, diagnostics
    )
