"""Human-seeded prototypes in the existing CIE Lab space, without label coercion."""

from collections.abc import Mapping, Sequence

import numpy as np

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.cv.team_classifier import (
    LAB_TOLERANCE,
    MIN_TEAM_SEPARATION,
    Appearance,
    TeamPrediction,
)

# A crop votes for a kit only when it is at most half as far from that prototype
# as from the other, within the same-colour tolerance (LAB_TOLERANCE), and its
# dominant colour covers at least half of the torso pixels. Fixed a priori; see
# docs/KPI_QUALITY_REPORT.md for the measured effect and sensitivity.
VOTE_DISTANCE_RATIO = 0.5
MIN_VOTE_QUALITY = 0.5


def fit_prototype(samples: Sequence[Appearance], settings: Settings) -> Appearance:
    if not samples or any(
        not np.isfinite(s.quality)
        or not settings.team_unknown_threshold <= s.quality <= 1
        for s in samples
    ):
        raise ValueError(
            "Select clear, consistent torso crops; a selected "
            "crop has weak color evidence."
        )
    colors = np.asarray([sample.color for sample in samples], dtype=np.float64)
    if (
        colors.shape != (len(samples), 3)
        or not np.isfinite(colors).all()
        or np.any(np.abs(colors) > 128)
    ):
        raise ValueError("A selected crop has invalid color evidence.")
    color = np.median(colors, axis=0)
    deviations = np.linalg.norm(colors - color, axis=1)
    # A robust center is not permission to silently discard a wrongly labelled
    # sample. All analyst examples must agree; ask for better examples otherwise.
    if np.any(deviations > LAB_TOLERANCE):
        raise ValueError(
            "Selected examples disagree in color. Use consistent samples for each team."
        )
    quality = float(np.mean([s.quality for s in samples])) * max(
        0.0, 1 - float(deviations.mean()) / LAB_TOLERANCE
    )
    if quality < settings.team_unknown_threshold:
        raise ValueError(
            "Selected examples have inconsistent lighting or "
            "background. Choose clearer crops."
        )
    return Appearance(tuple(map(float, color)), quality)


def validate_prototypes(prototypes: Mapping[TrackTeam, Appearance]) -> None:
    if set(prototypes) != {TrackTeam.TEAM_A, TrackTeam.TEAM_B}:
        raise ValueError("Provide examples for both teams.")
    values = np.asarray(
        [prototypes[t].color for t in (TrackTeam.TEAM_A, TrackTeam.TEAM_B)]
    )
    if (
        not np.isfinite(values).all()
        or np.linalg.norm(values[0] - values[1]) < MIN_TEAM_SEPARATION
    ):
        raise ValueError(
            "The selected team colors are too similar to separate reliably."
        )


def classify_seeded(
    evidence: Mapping[int, Sequence[Appearance]],
    prototypes: Mapping[TrackTeam, Appearance],
    settings: Settings,
) -> list[TeamPrediction]:
    """Require repeated, unopposed, clearly separable evidence for one user kit.

    Each crop votes for the prototype it clearly matches, or abstains when its
    colour is ambiguous, far from both kits (e.g. officials) or incoherent
    (background-heavy). Abstentions are never negative votes. A team needs at least
    the configured minimum of actual votes and no vote for the other team; nothing
    is duplicated or relaxed to reach the minimum. Confidence is the share of the
    track's samples that voted for the assigned team; margin is their mean
    1 - near/far distance ratio.
    """
    validate_prototypes(prototypes)
    centers = np.asarray(
        [prototypes[t].color for t in (TrackTeam.TEAM_A, TrackTeam.TEAM_B)]
    )
    results = []
    for track_id, samples in sorted(evidence.items()):
        votes: list[list[float]] = [[], []]
        for sample in samples:
            if (
                not np.isfinite((*sample.color, sample.quality)).all()
                or sample.quality < MIN_VOTE_QUALITY
            ):
                continue
            distances = np.linalg.norm(centers - np.asarray(sample.color), axis=1)
            label = int(distances.argmin())
            near, far = float(distances[label]), float(distances[1 - label])
            if near <= LAB_TOLERANCE and near <= VOTE_DISTANCE_RATIO * far:
                votes[label].append(1 - near / far)
        label = 0 if len(votes[0]) >= len(votes[1]) else 1
        count = len(votes[label])
        reason = None
        if votes[0] and votes[1]:
            reason = "conflicting_team_evidence"
        elif count < settings.team_min_samples:
            reason = "insufficient_consistent_samples"
        if reason:
            results.append(
                TeamPrediction(
                    track_id,
                    sample_count=len(samples),
                    rejection_reason=reason,
                    accepted_sample_count=count,
                    rejected_sample_count=len(samples) - count,
                )
            )
            continue
        results.append(
            TeamPrediction(
                track_id,
                (TrackTeam.TEAM_A, TrackTeam.TEAM_B)[label],
                count / len(samples),
                len(samples),
                float(np.mean(votes[label])),
                None,
                count,
                len(samples) - count,
            )
        )
    return results
