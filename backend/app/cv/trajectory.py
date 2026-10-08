"""Bounded, timestamp-aware quality filtering; no football movement metrics.

One isolated spike is rejected only when both neighboring steps are impossible
but the neighbors agree with each other. Ambiguous/persistent jumps split the
track. Rejected rows are retained, and never contribute to smoothing.
"""

import math
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, replace
from statistics import median

from app.core.config import Settings
from app.cv.coordinate_rows import CoordinateObservation
from app.cv.player_position import inside_pitch


@dataclass(frozen=True)
class TrajectoryObservation:
    raw: CoordinateObservation
    segment_id: int | None = None
    clean: tuple[float, float] | None = None
    status: str = "accepted"

    @property
    def usable(self) -> bool:
        return self.clean is not None


def _plausible(
    first: CoordinateObservation,
    second: CoordinateObservation,
    settings: Settings,
) -> bool:
    dt = second.timestamp - first.timestamp
    # Compare distance with allowed travel rather than dividing by tiny/zero dt.
    return dt > 0 and math.dist(first.pitch, second.pitch) <= (
        settings.trajectory_max_plausible_speed_mps * dt
    )


def _temporal(rows: Iterator[CoordinateObservation]) -> Iterator[TrajectoryObservation]:
    last_time, last_frame = -1.0, -1
    for row in rows:
        if row.timestamp < 0 or row.timestamp <= last_time or row.frame <= last_frame:
            yield TrajectoryObservation(
                row, status="invalid_temporal" if row.inside_pitch else "outside_pitch"
            )
            continue
        last_time, last_frame = row.timestamp, row.frame
        yield TrajectoryObservation(
            row, status="accepted" if row.inside_pitch else "outside_pitch"
        )


def _segments(
    rows: Iterator[CoordinateObservation],
    settings: Settings,
) -> Iterator[TrajectoryObservation]:
    prepared = _temporal(rows)
    current = next(prepared, None)
    previous = None
    segment = 0
    discontinuity = False
    while current is not None:
        following = next(prepared, None)
        raw = current.raw
        if current.status != "accepted":
            discontinuity |= current.status == "invalid_temporal"
        else:
            gap = raw.timestamp - previous.timestamp if previous else math.inf
            start = (
                previous is None
                or discontinuity
                or (gap > settings.trajectory_max_gap_seconds)
            )
            if not start and not _plausible(previous, raw, settings):
                isolated = (
                    following is not None
                    and following.status == "accepted"
                    and following.raw.timestamp - previous.timestamp
                    <= settings.trajectory_max_gap_seconds
                    and not _plausible(raw, following.raw, settings)
                    and _plausible(previous, following.raw, settings)
                )
                if isolated:
                    current = replace(current, status="jump_outlier")
                else:
                    start = True
            if current.status == "accepted":
                if start:
                    segment += 1
                current = replace(
                    current,
                    segment_id=segment,
                    clean=raw.pitch,
                    status="segment_start" if start else "accepted",
                )
                previous, discontinuity = raw, False
        yield current
        current = following


def _smooth(
    window: list[TrajectoryObservation],
    previous: TrajectoryObservation | None,
    settings: Settings,
    length: float,
    width: float,
) -> TrajectoryObservation:
    center = window[len(window) // 2]
    first, last = window[0].raw, window[-1].raw
    span = last.timestamp - first.timestamp
    if len(window) == 1 or span <= 0:
        return center

    def baseline(row: CoordinateObservation, axis: int) -> float:
        weight = (row.timestamp - first.timestamp) / span
        return first.pitch[axis] + weight * (last.pitch[axis] - first.pitch[axis])

    # Median residual from a timestamp-linear local baseline preserves constant
    # motion even at irregular cadence. Move only halfway toward this estimate.
    target = tuple(
        baseline(center.raw, axis)
        + median(p.raw.pitch[axis] - baseline(p.raw, axis) for p in window)
        for axis in (0, 1)
    )
    delta = tuple((target[a] - center.raw.pitch[a]) / 2 for a in (0, 1))
    shift = math.hypot(*delta)
    if shift == 0 or settings.trajectory_smoothing_max_shift_metres == 0:
        return center
    scale = min(1.0, settings.trajectory_smoothing_max_shift_metres / shift)
    clean = tuple(center.raw.pitch[a] + scale * delta[a] for a in (0, 1))
    if not inside_pitch(*clean, length, width):
        return center  # Never clamp to a boundary.
    candidate = replace(center.raw, pitch=clean)
    next_raw = window[len(window) // 2 + 1].raw
    if (
        previous is not None
        and not _plausible(
            replace(previous.raw, pitch=previous.clean), candidate, settings
        )
    ) or not _plausible(candidate, next_raw, settings):
        return center
    if math.dist(clean, center.raw.pitch) <= 1e-9:
        return center
    return replace(center, clean=clean, status="smoothed")


def clean_track(
    rows: Iterator[CoordinateObservation],
    settings: Settings,
    length: float,
    width: float,
) -> Iterator[TrajectoryObservation]:
    """Input is one track sorted by timestamp/frame/source row, without inference.

    Full short windows only; segment/run endpoints remain unchanged. Any rejected
    row ends the smoothing window, so it cannot influence neighboring positions.
    """
    size = settings.trajectory_smoothing_window
    radius = size // 2
    buffer: deque[TrajectoryObservation] = deque()
    started = False
    previous = None
    for point in _segments(rows, settings):
        if not point.usable or (buffer and point.segment_id != buffer[-1].segment_id):
            yield from list(buffer)[radius if started else 0 :]
            buffer.clear()
            started, previous = False, None
        if not point.usable:
            yield point
            continue
        buffer.append(point)
        if len(buffer) == size:
            values = list(buffer)
            if not started:
                for edge in values[:radius]:
                    yield edge
                    previous = edge
                started = True
            smoothed = _smooth(values, previous, settings, length, width)
            yield smoothed
            previous = smoothed
            buffer.popleft()
    yield from list(buffer)[radius if started else 0 :]
