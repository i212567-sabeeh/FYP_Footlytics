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
    aggregate_appearance,
)


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
    """Require repeated, unopposed evidence against both user-labelled prototypes.

    Background-heavy/ambiguous frames do not become artificial negative team votes.
    Keep at least the configured minimum actual supporting frames; any confident
    opposite-team observation rejects the track. Then aggregate only this coherent
    evidence with the existing robust median and consistency penalty. No thresholds
    are lowered and no sample is duplicated to meet the minimum.
    """
    validate_prototypes(prototypes)
    centers = np.asarray(
        [prototypes[t].color for t in (TrackTeam.TEAM_A, TrackTeam.TEAM_B)]
    )
    separation = min(
        1.0, float(np.linalg.norm(centers[0] - centers[1])) / (2 * MIN_TEAM_SEPARATION)
    )

    def score_color(appearance):
        distances = np.linalg.norm(centers - appearance.color, axis=1)
        label = int(distances.argmin())
        near, far = float(distances[label]), float(distances[1 - label])
        margin = max(0.0, 1 - near / max(far, 1e-6))
        score = (
            appearance.quality
            * separation
            * margin
            * max(0.0, 1 - near / LAB_TOLERANCE)
        )
        return label, float(np.clip(score, 0, 1)), margin

    results = []
    for track_id, samples in sorted(evidence.items()):
        support: list[list[Appearance]] = [[], []]
        for sample in samples:
            if not np.isfinite((*sample.color, sample.quality)).all():
                continue
            label, score, _ = score_color(sample)
            if score >= settings.team_unknown_threshold:
                support[label].append(sample)
        label = 0 if len(support[0]) >= len(support[1]) else 1
        count = len(support[label])
        reason = None
        if support[0] and support[1]:
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
        appearance = aggregate_appearance(support[label], settings)
        if appearance is None:
            results.append(
                TeamPrediction(
                    track_id,
                    sample_count=len(samples),
                    rejection_reason="invalid_appearance",
                )
            )
            continue
        predicted, score, margin = score_color(appearance)
        team = (TrackTeam.TEAM_A, TrackTeam.TEAM_B)[label]
        if predicted != label or score < settings.team_unknown_threshold:
            team, reason = TrackTeam.UNKNOWN, "inconsistent_color_evidence"
        results.append(
            TeamPrediction(
                track_id,
                team,
                score,
                len(samples),
                margin,
                reason,
                count,
                len(samples) - count,
            )
        )
    return results
