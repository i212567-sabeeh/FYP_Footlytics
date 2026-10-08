"""Protected, paginated track metrics and sparse occupancy from current bundles."""

import csv
import math
import re
from contextlib import closing
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import STAFF_ROLES, has_roles
from app.core.config import Settings
from app.core.jobs import JobType
from app.models.media import MatchVideo, ProcessingJob
from app.models.user import User
from app.schemas.football import Page
from app.schemas.player_analytics import (
    AnalyticsSummary,
    TrackAnalytics,
    TrackAnalyticsRead,
    TrackHeatmapRead,
)
from app.services.analytics_artifacts import MODELS, read_rows
from app.services.domain_common import DomainError
from app.services.match_service import get_match
from app.services.result_inputs import SUCCESS
from app.services.storage_service import StorageService
from app.services.tracking_inputs import file_version
from app.services.trajectory_service import current_trajectories

UNAVAILABLE = "The player analytics bundle or summary is invalid or unavailable."


@dataclass(frozen=True)
class AnalyticsSource:
    job: ProcessingJob
    summary: AnalyticsSummary
    paths: dict[str, Path]
    video_duration_seconds: float | None = None

    @property
    def identity(self) -> dict:
        return {
            "match_id": self.job.match_id,
            "video_id": self.job.video_id,
            "job_id": self.job.id,
            "trajectory_job_id": self.summary.trajectory_job_id,
        }


def _current(
    session: Session, user: User, match_id: int, settings: Settings
) -> AnalyticsSource:
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(403, "Staff access is required for Track-ID analytics.")
    match = get_match(session, user, match_id)
    source = current_trajectories(session, match, settings)
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == match_id,
            ProcessingJob.video_id == source.job.video_id,
            ProcessingJob.job_type == JobType.PLAYER_ANALYTICS,
            ProcessingJob.status.in_(SUCCESS),
        )
        .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
    )
    if job is None:
        raise DomainError(409, "No player analytics results are available yet.")
    if job.trajectory_snapshot != source.version:
        raise DomainError(
            409, "Player analytics are stale. Analyze the current cleaned trajectories."
        )
    try:
        data = AnalyticsSummary.model_validate(job.analytics_summary)
        if (
            data.trajectory_job_id != source.job.id
            or data.trajectory_attempt != source.job.attempt
            or any(
                getattr(data, key) != getattr(source.summary, key)
                for key in (
                    "source_rows",
                    "usable_rows",
                    "rejected_rows",
                    "unique_tracks",
                    "pitch_length_metres",
                    "pitch_width_metres",
                    "max_plausible_speed_mps",
                    "max_gap_seconds",
                )
            )
        ):
            raise ValueError("Inconsistent analytics provenance")
        prefix = f"analytics/matches/{match_id}/videos/{job.video_id}/jobs/{job.id}/"
        relative = job.artifact_relative_path or ""
        if not re.fullmatch(rf"{prefix}attempt-{job.attempt}-[0-9a-f]{{32}}", relative):
            raise ValueError("Invalid bundle location")
        versions = job.analytics_summary["artifact_versions"]
        if set(versions) != set(MODELS):
            raise ValueError("Incomplete artifact manifest")
        storage = StorageService(settings)
        paths = {}
        for name, model in MODELS.items():
            path = storage.resolve(f"{relative}/{name}.csv")
            if file_version(path) != versions[name]:
                raise ValueError("Changed analytics artifact")
            with path.open(newline="", encoding="utf-8") as stream:
                if tuple(next(csv.reader([stream.readline(4096)]), ())) != tuple(
                    model.model_fields
                ):
                    raise ValueError("Invalid analytics columns")
            paths[name] = path
    except (OSError, ValueError, TypeError, KeyError, csv.Error, DomainError):
        raise DomainError(409, UNAVAILABLE) from None
    video = session.get(MatchVideo, job.video_id)
    return AnalyticsSource(job, data, paths, video.duration_seconds if video else None)


def _rows(source: AnalyticsSource, name: str):
    try:
        yield from read_rows(source.paths[name], name)
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        raise DomainError(409, UNAVAILABLE) from None


def observation_coverage(observed: float, video_duration: float | None) -> dict:
    """Describe measured intervals relative to the whole source, never fill gaps.

    The 15 s / 20% flags are presentation cautions, not validity or quality scores.
    An unknown or inconsistent denominator is reported as unavailable, not clipped.
    """
    duration = (
        video_duration
        if video_duration is not None
        and math.isfinite(video_duration)
        and video_duration > 0
        else None
    )
    percent = (
        100 * observed / duration
        if duration is not None and observed <= duration
        else None
    )
    if observed <= 0:
        warning = "No usable observed intervals."
    elif percent is None:
        warning = (
            "Coverage is unavailable; the video duration is missing or inconsistent."
        )
    elif observed < 15:
        warning = (
            "Short track fragment (under 15 seconds); "
            "this is not complete player positioning."
        )
    elif percent < 20:
        warning = (
            "Low coverage (under 20% of this video); "
            "this is not complete player positioning."
        )
    else:
        warning = None
    return {
        "video_duration_seconds": duration,
        "observed_coverage_percent": percent,
        "coverage_warning": warning,
    }


def list_players(
    session: Session,
    user: User,
    match_id: int,
    settings: Settings,
    offset: int,
    limit: int,
):
    source = _current(session, user, match_id, settings)
    with closing(_rows(source, "players")) as rows:
        items = [
            TrackAnalyticsRead(
                **row.model_dump(),
                **source.identity,
                **observation_coverage(
                    row.active_duration_seconds, source.video_duration_seconds
                ),
            )
            for row in islice(rows, offset, offset + limit)
        ]
    return Page[TrackAnalyticsRead](
        items=items, total=source.summary.unique_tracks, offset=offset, limit=limit
    )


def _track(source: AnalyticsSource, track_id: int) -> TrackAnalytics:
    with closing(_rows(source, "players")) as rows:
        for row in rows:
            if row.track_id == track_id:
                return row
            if row.track_id > track_id:
                break
    raise DomainError(404, "Track analytics not found")


def get_player(
    session: Session, user: User, match_id: int, track_id: int, settings: Settings
):
    source = _current(session, user, match_id, settings)
    track = _track(source, track_id)
    return TrackAnalyticsRead(
        **track.model_dump(),
        **source.identity,
        **observation_coverage(
            track.active_duration_seconds, source.video_duration_seconds
        ),
    )


def get_heatmap(
    session: Session, user: User, match_id: int, track_id: int, settings: Settings
):
    source = _current(session, user, match_id, settings)
    track = _track(source, track_id)
    cells = []
    with closing(_rows(source, "heatmaps")) as rows:
        for row in rows:
            if row.track_id > track_id:
                break
            if row.track_id == track_id:
                cells.append(row)
                if (
                    len(cells)
                    > source.summary.heatmap_bins_x * source.summary.heatmap_bins_y
                    or row.x_bin >= source.summary.heatmap_bins_x
                    or row.y_bin >= source.summary.heatmap_bins_y
                ):
                    raise DomainError(409, UNAVAILABLE)
    if not math.isclose(
        sum(cell.occupancy_seconds for cell in cells),
        track.active_duration_seconds,
        abs_tol=1e-9,
    ):
        raise DomainError(409, UNAVAILABLE)
    return TrackHeatmapRead(
        **source.identity,
        track_id=track_id,
        pitch_length_metres=source.summary.pitch_length_metres,
        pitch_width_metres=source.summary.pitch_width_metres,
        bins_x=source.summary.heatmap_bins_x,
        bins_y=source.summary.heatmap_bins_y,
        total_occupancy_seconds=track.active_duration_seconds,
        **observation_coverage(
            track.active_duration_seconds, source.video_duration_seconds
        ),
        cells=cells,
    )
