"""Piecewise observed movement; bounded state per track and no upstream CV."""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import groupby

from pydantic import BaseModel

from app.analytics.heatmaps import OccupancyGrid
from app.analytics.trajectory_rows import CleanObservation
from app.core.config import Settings
from app.schemas.player_analytics import MovementInterval, SprintEvent, TrackAnalytics
from app.schemas.trajectories import TrajectorySummary

Writer = Callable[[str, BaseModel], None]


@dataclass
class AnalyticsRun:
    source_rows: int = 0
    usable_rows: int = 0
    rejected_rows: int = 0
    unique_tracks: int = 0
    valid_intervals: int = 0
    excluded_intervals: int = 0
    sprint_events: int = 0
    heatmap_cells: int = 0


def calculate_players(
    observations: Iterable[CleanObservation],
    source: TrajectorySummary,
    settings: Settings,
    *,
    write: Writer,
    progress: Callable[[int, int], None],
) -> AnalyticsRun:
    """Phase 10 is ordered by track/time/frame. Never buffer a whole track/video.

    An interval requires adjacent usable observations in one segment. Rejection
    ends continuity even when Phase 10 assigned the same segment on either side.
    Physical limits come from the *saved cleaning run*, not newly changed settings.
    """
    run = AnalyticsRun()
    for track_id, points in groupby(observations, key=lambda row: row.track_id):
        _track(track_id, points, source, settings, run, write, progress)
    return run


def _track(
    track_id: int,
    points: Iterable[CleanObservation],
    source: TrajectorySummary,
    settings: Settings,
    run: AnalyticsRun,
    write: Writer,
    progress: Callable[[int, int], None],
) -> None:
    """Measure one track.

    A continuous run is consecutive valid usable pairs in one segment. Movement
    is measured between window endpoints at least PLAYER_SPEED_WINDOW_SECONDS
    apart (0 = every pair): `anchor` opens the current window and a closed window
    is held until the next one closes, so the run's remainder can extend it.
    """
    window = settings.player_speed_window_seconds
    grid = OccupancyGrid(
        source.pitch_length_metres,
        source.pitch_width_metres,
        settings.player_heatmap_bins_x,
        settings.player_heatmap_bins_y,
    )
    previous = anchor = None
    held: tuple[CleanObservation, CleanObservation] | None = None
    last_segment = segment_count = usable = interval_count = excluded = 0
    first_frame = last_frame = first_time = last_time = None
    duration = distance = 0.0
    maximum = None
    sprint: SprintEvent | None = None
    sprint_count = 0
    sprint_distance = sprint_duration = 0.0

    def finish_sprint() -> None:
        nonlocal sprint, sprint_count, sprint_distance, sprint_duration
        if sprint is not None and (
            sprint.duration_seconds >= settings.player_sprint_min_duration_seconds
            or math.isclose(
                sprint.duration_seconds,
                settings.player_sprint_min_duration_seconds,
                rel_tol=1e-9,
                abs_tol=0,
            )
        ):
            write("sprints", sprint)
            sprint_count += 1
            sprint_distance += sprint.distance_metres
            sprint_duration += sprint.duration_seconds
        sprint = None

    def measure(start: CleanObservation, end: CleanObservation) -> None:
        nonlocal interval_count, distance, duration, maximum, sprint
        dt = end.timestamp - start.timestamp
        step = math.dist(start.clean, end.clean)
        speed = step / dt
        interval = MovementInterval(
            track_id=track_id,
            segment_id=end.segment_id,
            start_frame=start.frame,
            end_frame=end.frame,
            start_timestamp=start.timestamp,
            end_timestamp=end.timestamp,
            start_x=start.clean[0],
            start_y=start.clean[1],
            end_x=end.clean[0],
            end_y=end.clean[1],
            dt_seconds=dt,
            distance_metres=step,
            speed_mps=speed,
            speed_kmh=speed * 3.6,
            above_sprint_threshold=speed >= settings.player_sprint_speed_threshold_mps,
        )
        write("intervals", interval)
        interval_count += 1
        distance += step
        duration += dt
        maximum = speed if maximum is None else max(maximum, speed)
        grid.add(start.clean, dt)
        if interval.above_sprint_threshold:
            sprint = SprintEvent(
                track_id=track_id,
                segment_id=end.segment_id,
                start_frame=sprint.start_frame if sprint else start.frame,
                end_frame=end.frame,
                start_timestamp=sprint.start_timestamp if sprint else start.timestamp,
                end_timestamp=end.timestamp,
                duration_seconds=(sprint.duration_seconds if sprint else 0) + dt,
                distance_metres=(sprint.distance_metres if sprint else 0) + step,
                max_speed_mps=max(sprint.max_speed_mps, speed) if sprint else speed,
            )
        else:
            finish_sprint()

    def end_run() -> None:
        """Measure the held window up to the run's last valid observation.

        A run shorter than the speed window yields no measurement: its
        displacement would be bounding-box jitter rather than movement.
        """
        nonlocal held
        if held is not None:
            measure(held[0], previous)
            held = None
        finish_sprint()

    for point in points:
        run.source_rows += 1
        if point.clean is None:
            run.rejected_rows += 1
            end_run()
            previous = anchor = None
        else:
            run.usable_rows += 1
            usable += 1
            first_frame = (
                point.frame if first_frame is None else min(first_frame, point.frame)
            )
            last_frame = (
                point.frame if last_frame is None else max(last_frame, point.frame)
            )
            first_time = (
                point.timestamp
                if first_time is None
                else min(first_time, point.timestamp)
            )
            last_time = (
                point.timestamp
                if last_time is None
                else max(last_time, point.timestamp)
            )
            if point.segment_id != last_segment:
                segment_count += 1
                last_segment = point.segment_id
            if previous is None or point.segment_id != previous.segment_id:
                end_run()
                previous = anchor = point
            else:
                dt = point.timestamp - previous.timestamp
                step = math.dist(previous.clean, point.clean)
                speed = step / dt if dt > 0 else math.inf
                if (
                    not math.isfinite(speed)
                    or not 0 <= speed <= source.max_plausible_speed_mps
                    or not 0 < dt <= source.max_gap_seconds
                    or point.frame <= previous.frame
                ):
                    excluded += 1
                    end_run()
                    previous = anchor = (
                        point if dt > 0 and point.frame > previous.frame else None
                    )
                else:
                    previous = point
                    # Tolerance keeps e.g. five 0.04 s frames equal to 0.2 s.
                    if point.timestamp - anchor.timestamp + 1e-9 >= window:
                        if held is not None:
                            measure(*held)
                        held = (anchor, point)
                        anchor = point
                        if not window:
                            # Nothing can extend a per-pair measurement.
                            measure(*held)
                            held = None
        if run.source_rows % 256 == 0:
            progress(run.source_rows, source.source_rows)
    end_run()
    average = distance / duration if duration else None
    write(
        "players",
        TrackAnalytics(
            track_id=track_id,
            first_frame=first_frame,
            last_frame=last_frame,
            first_timestamp=first_time,
            last_timestamp=last_time,
            segment_count=segment_count,
            usable_observation_count=usable,
            valid_interval_count=interval_count,
            excluded_interval_count=excluded,
            active_duration_seconds=duration,
            total_distance_metres=distance,
            average_speed_mps=average,
            average_speed_kmh=average * 3.6 if average is not None else None,
            max_speed_mps=maximum,
            max_speed_kmh=maximum * 3.6 if maximum is not None else None,
            sprint_count=sprint_count,
            sprint_distance_metres=sprint_distance,
            sprint_duration_seconds=sprint_duration,
        ),
    )
    for cell in grid.cells(track_id, duration):
        write("heatmaps", cell)
        run.heatmap_cells += 1
    run.unique_tracks += 1
    run.valid_intervals += interval_count
    run.excluded_intervals += excluded
    run.sprint_events += sprint_count
    progress(run.source_rows, source.source_rows)
