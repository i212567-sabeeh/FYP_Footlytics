"""Protected summaries and bounded series from one current tactical bundle."""

import csv
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
from app.models.media import ProcessingJob
from app.models.user import User
from app.schemas.football import Page
from app.schemas.team_analytics import (
    TacticalTeam,
    TacticsSummary,
    TeamAnalyticsRead,
    TeamSnapshot,
)
from app.services.analytics_artifacts import read_rows
from app.services.domain_common import DomainError
from app.services.match_service import get_match
from app.services.result_inputs import SUCCESS
from app.services.storage_service import StorageService
from app.services.tactics_artifacts import MODELS, TacticsArtifacts
from app.services.tactics_inputs import current_tactics_inputs
from app.services.tracking_inputs import file_version

UNAVAILABLE = "The team tactical analytics bundle is invalid or unavailable."


@dataclass(frozen=True)
class TacticsSource:
    job: ProcessingJob
    summary: TacticsSummary
    paths: dict[str, Path]


def _current(
    session: Session, user: User, match_id: int, settings: Settings
) -> TacticsSource:
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(403, "Staff access is required for team analytics.")
    inputs = current_tactics_inputs(
        session, get_match(session, user, match_id), settings
    )
    source = inputs.trajectories
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == match_id,
            ProcessingJob.video_id == source.job.video_id,
            ProcessingJob.job_type == JobType.TEAM_TACTICAL_ANALYTICS,
            ProcessingJob.status.in_(SUCCESS),
        )
        .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
    )
    if job is None:
        raise DomainError(409, "No team tactical analytics are available yet.")
    if (
        job.trajectory_snapshot != source.version
        or job.assignment_snapshot != inputs.assignment_version
    ):
        raise DomainError(
            409,
            "Team analytics are stale. "
            "Analyze the current trajectories and assignments.",
        )
    try:
        data = TacticsSummary.model_validate(job.tactics_summary)
        if (
            data.trajectory_job_id != source.job.id
            or data.trajectory_attempt != source.job.attempt
            or any(
                getattr(data, key) != getattr(source.summary, key)
                for key in (
                    "source_rows",
                    "usable_rows",
                    "rejected_rows",
                    "pitch_length_metres",
                    "pitch_width_metres",
                )
            )
        ):
            raise ValueError("Inconsistent tactical provenance")
        prefix = (
            f"{TacticsArtifacts.prefix}/matches/{match_id}/"
            f"videos/{job.video_id}/jobs/{job.id}/"
        )
        relative = job.artifact_relative_path or ""
        if not re.fullmatch(rf"{prefix}attempt-{job.attempt}-[0-9a-f]{{32}}", relative):
            raise ValueError("Invalid bundle location")
        versions = job.tactics_summary["artifact_versions"]
        if set(versions) != set(MODELS):
            raise ValueError("Incomplete artifact manifest")
        storage, paths = StorageService(settings), {}
        for name, model in MODELS.items():
            path = storage.resolve(f"{relative}/{name}.csv")
            if file_version(path) != versions[name]:
                raise ValueError("Changed artifact")
            with path.open(newline="", encoding="utf-8") as stream:
                if tuple(next(csv.reader([stream.readline(4096)]), ())) != tuple(
                    model.model_fields
                ):
                    raise ValueError("Invalid analytics columns")
            paths[name] = path
    except (OSError, ValueError, TypeError, KeyError, csv.Error, DomainError):
        raise DomainError(409, UNAVAILABLE) from None
    return TacticsSource(job, data, paths)


def _rows(source: TacticsSource, name: str):
    try:
        yield from read_rows(source.paths[name], name, MODELS)
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        raise DomainError(409, UNAVAILABLE) from None


def _summaries(source: TacticsSource):
    with closing(_rows(source, "team_tactics_summary")) as rows:
        teams = list(islice(rows, 3))
    if [row.team for row in teams] != ["team_a", "team_b"] or any(
        row.valid_snapshots + row.insufficient_snapshots
        != source.summary.observed_frames
        for row in teams
    ):
        raise DomainError(409, UNAVAILABLE)
    return teams


def get_summary(session: Session, user: User, match_id: int, settings: Settings):
    source = _current(session, user, match_id, settings)
    return TeamAnalyticsRead(
        match_id=match_id,
        video_id=source.job.video_id,
        job_id=source.job.id,
        summary=source.summary,
        teams=_summaries(source),
    )


def get_team(
    session: Session, user: User, match_id: int, team: TacticalTeam, settings: Settings
):
    return next(
        row
        for row in _summaries(_current(session, user, match_id, settings))
        if row.team == team
    )


def get_series(
    session: Session,
    user: User,
    match_id: int,
    team: TacticalTeam,
    settings: Settings,
    offset: int,
    limit: int,
):
    source = _current(session, user, match_id, settings)
    with closing(_rows(source, "team_tactics_frames")) as rows:
        items = list(
            islice((row for row in rows if row.team == team), offset, offset + limit)
        )
    return Page[TeamSnapshot](
        items=items, total=source.summary.observed_frames, offset=offset, limit=limit
    )
