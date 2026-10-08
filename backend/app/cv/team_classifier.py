"""Bounded jersey evidence and deterministic two-color clustering on CPU.

Scores describe color evidence quality, not calibrated probabilities or player
identity. No model, detector, tracker or full-frame history is loaded here.
"""

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from app.core.config import Settings
from app.core.teams import TrackTeam

Image = NDArray[np.uint8]
Color = tuple[float, float, float]

# Central torso excludes head, legs and box edges without masking green jerseys.
JERSEY_REGION = (0.2, 0.18, 0.8, 0.55)
FEATURE_MAX_EDGE = 64
LAB_TOLERANCE = 25.0
MIN_TEAM_SEPARATION = 20.0
KMEANS_ITERATIONS = 30
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Appearance:
    color: Color
    quality: float


@dataclass(frozen=True)
class TeamPrediction:
    track_id: int
    team: TrackTeam = TrackTeam.UNKNOWN
    confidence: float = 0.0
    sample_count: int = 0
    margin: float | None = None
    rejection_reason: str | None = None
    accepted_sample_count: int = 0
    rejected_sample_count: int = 0


def jersey_bounds(
    width: int, height: int, box: Sequence[float], settings: Settings
) -> tuple[int, int, int, int] | None:
    """Preserve torso proportions, clip to the image, reject invisible/tiny crops."""
    try:
        x1, y1, x2, y2 = box
        if (
            not all(math.isfinite(v) for v in box)
            or x1 >= x2
            or y1 >= y2
            or x2 <= 0
            or y2 <= 0
            or x1 >= width
            or y1 >= height
        ):
            return None
        left, top, right, bottom = JERSEY_REGION
        bounds = (
            max(0, math.ceil(x1 + left * (x2 - x1))),
            max(0, math.ceil(y1 + top * (y2 - y1))),
            min(width, math.floor(x1 + right * (x2 - x1))),
            min(height, math.floor(y1 + bottom * (y2 - y1))),
        )
        a, b, c, d = bounds
        if (
            c - a < settings.team_min_crop_width
            or d - b < settings.team_min_crop_height
        ):
            return None
        return bounds
    except (ValueError, TypeError, OverflowError):
        return None


def _valid_image(image: Image) -> bool:
    return (
        isinstance(image, np.ndarray)
        and image.ndim == 3
        and image.shape[2] == 3
        and image.dtype == np.uint8
        and image.size > 0
    )


def jersey_crop(image: Image, box: Sequence[float], settings: Settings) -> Image | None:
    if not _valid_image(image):
        return None
    bounds = jersey_bounds(image.shape[1], image.shape[0], box, settings)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    return image[top:bottom, left:right]


def jersey_feature(crop: Image) -> Appearance | None:
    """Median CIE Lab plus the fraction of pixels near that color.

    Float BGR in [0, 1] gives L in [0, 100] and signed a/b, avoiding the
    incompatible channel scales of OpenCV's 8-bit Lab encoding.
    """
    if not _valid_image(crop):
        return None
    try:
        height, width = crop.shape[:2]
        scale = min(1.0, FEATURE_MAX_EDGE / max(width, height))
        if scale < 1:
            crop = cv2.resize(
                crop,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        pixels = cv2.cvtColor(crop.astype(np.float32) / 255, cv2.COLOR_BGR2Lab).reshape(
            -1, 3
        )
    except cv2.error:
        logger.warning("A sampled jersey crop could not be measured", exc_info=True)
        return None
    color = np.median(pixels, axis=0)
    quality = float(np.mean(np.linalg.norm(pixels - color, axis=1) <= LAB_TOLERANCE))
    return Appearance(tuple(float(v) for v in color), quality)


def aggregate_appearance(
    samples: Sequence[Appearance], settings: Settings
) -> Appearance | None:
    if len(samples) < settings.team_min_samples:
        return None
    colors = np.asarray([sample.color for sample in samples], dtype=np.float64)
    quality = np.asarray([sample.quality for sample in samples], dtype=np.float64)
    if (
        colors.shape != (len(samples), 3)
        or not np.isfinite(colors).all()
        or np.any(np.abs(colors) > 128)
        or not np.isfinite(quality).all()
        or np.any((quality < 0) | (quality > 1))
    ):
        return None
    median = np.median(colors, axis=0)
    # Mean deviation penalizes frequent kit/background switches, even when the
    # median itself looks plausible. Each sampled frame has equal weight.
    spread = float(np.mean(np.linalg.norm(colors - median, axis=1)))
    score = float(quality.mean()) * max(0.0, 1.0 - spread / LAB_TOLERANCE)
    return Appearance(tuple(float(v) for v in median), score)


def _two_centroids(colors: NDArray[np.float64]) -> NDArray[np.float64] | None:
    """Lloyd K-Means (k=2), deterministic initialization and ties; no RNG.

    Sort by Lab, start at the first color and the farthest color, then repeat
    nearest-centroid assignment and arithmetic means. Empty/merged clusters
    cannot establish two teams. Memory is linear in the number of tracks.
    """
    colors = colors[np.lexsort((colors[:, 2], colors[:, 1], colors[:, 0]))]
    first = colors[0]
    second = colors[np.argmax(np.linalg.norm(colors - first, axis=1))]
    centers = np.stack((first, second))
    for _ in range(KMEANS_ITERATIONS):
        distances = np.linalg.norm(colors[:, None, :] - centers[None, :, :], axis=2)
        labels = distances.argmin(axis=1)
        if not np.any(labels == 0) or not np.any(labels == 1):
            return None
        updated = np.stack([colors[labels == label].mean(axis=0) for label in (0, 1)])
        converged = np.allclose(updated, centers, rtol=0, atol=1e-6)
        centers = updated
        if converged:
            break
    if np.linalg.norm(centers[0] - centers[1]) < MIN_TEAM_SEPARATION:
        return None
    # Team has no configured kit-color fields. Ascending (L,a,b) provides stable
    # A/B labels for the same evidence; it does not infer the actual club identity.
    return centers[np.lexsort((centers[:, 2], centers[:, 1], centers[:, 0]))]


def classify_tracks(
    evidence: Mapping[int, Sequence[Appearance]],
    settings: Settings,
    *,
    diagnostics: dict | None = None,
) -> list[TeamPrediction]:
    predictions = {
        track_id: TeamPrediction(
            track_id,
            sample_count=len(evidence[track_id]),
            rejection_reason="insufficient_samples"
            if len(evidence[track_id]) < settings.team_min_samples
            else "inconsistent_or_ambiguous_color",
        )
        for track_id in sorted(evidence)
    }
    audit = diagnostics if diagnostics is not None else {}
    sample_quality = [
        sample.quality for samples in evidence.values() for sample in samples
    ]
    audit.update(
        {
            "insufficient_sample_tracks": 0,
            "inconsistent_evidence_tracks": 0,
            "eligible_tracks": 0,
            "cluster_separation_lab": None,
            "low_margin_tracks": 0,
            "median_sample_quality": float(np.median(sample_quality))
            if sample_quality
            else None,
            "median_samples_per_track": float(
                np.median([len(v) for v in evidence.values()])
            )
            if evidence
            else None,
        }
    )
    valid = {}
    for track_id in predictions:
        appearance = aggregate_appearance(evidence[track_id], settings)
        if len(evidence[track_id]) < settings.team_min_samples:
            audit["insufficient_sample_tracks"] += 1
        elif appearance is None or appearance.quality < settings.team_unknown_threshold:
            audit["inconsistent_evidence_tracks"] += 1
        else:
            valid[track_id] = appearance
    audit["eligible_tracks"] = len(valid)
    if len(valid) < 2:
        return list(predictions.values())
    centers = _two_centroids(
        np.asarray([v.color for v in valid.values()], dtype=np.float64)
    )
    if centers is None:
        return list(predictions.values())
    separation = float(np.linalg.norm(centers[0] - centers[1]))
    audit["cluster_separation_lab"] = separation
    separation_quality = min(1.0, separation / (2 * MIN_TEAM_SEPARATION))
    for track_id, appearance in valid.items():
        distances = np.linalg.norm(centers - appearance.color, axis=1)
        label = int(distances.argmin())
        near, far = float(distances[label]), float(distances[1 - label])
        margin = max(0.0, 1.0 - near / max(far, 1e-6))
        closeness = max(0.0, 1.0 - near / LAB_TOLERANCE)
        score = float(
            np.clip(appearance.quality * separation_quality * margin * closeness, 0, 1)
        )
        team = (TrackTeam.TEAM_A, TrackTeam.TEAM_B)[label]
        if score < settings.team_unknown_threshold:
            team = TrackTeam.UNKNOWN
            audit["low_margin_tracks"] += 1
        predictions[track_id] = TeamPrediction(
            track_id,
            team,
            score,
            len(evidence[track_id]),
            margin,
            "ambiguous_color" if team == TrackTeam.UNKNOWN else None,
        )
    return list(predictions.values())
