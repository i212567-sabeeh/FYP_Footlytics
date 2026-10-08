"""Protected current report and small summary exports; saved inputs are read-only."""

import csv
import io
import math
import re
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.jobs import JobStatus, JobType
from app.models.media import ProcessingJob
from app.models.user import User
from app.reports.builder import team_label
from app.reports.data import read_players
from app.schemas.reports import ReportStatus, ReportSummary
from app.schemas.team_analytics import TeamTacticalSummary
from app.services import team_analytics_service
from app.services.domain_common import DomainError
from app.services.report_inputs import capture_inputs, reader_match
from app.services.storage_service import StorageService
from app.services.tracking_inputs import file_version

PLAYER_COLUMNS = [
    "track_id",
    "effective_team",
    "total_distance_metres",
    "active_duration_seconds",
    "average_speed_mps",
    "average_speed_kmh",
    "max_speed_mps",
    "max_speed_kmh",
    "sprint_count",
    "sprint_distance_metres",
    "sprint_duration_seconds",
]
TEAM_COLUMNS = list(TeamTacticalSummary.model_fields)


def _artifact(
    job: ProcessingJob, settings: Settings
) -> tuple[Path, ReportSummary] | None:
    relative = job.artifact_relative_path or ""
    expected = (
        rf"reports/matches/{job.match_id}/videos/{job.video_id}/jobs/{job.id}/"
        rf"attempt-{job.attempt}-[0-9a-f]{{32}}\.pdf"
    )
    if not re.fullmatch(expected, relative):
        return None
    try:
        summary = ReportSummary.model_validate(job.report_summary)
        path = StorageService(settings).resolve(relative)
        if (
            not path.is_file()
            or file_version(path) != job.report_summary.get("artifact_version")
            or path.stat().st_size != summary.size_bytes
        ):
            return None
        return path, summary
    except (OSError, ValueError, ValidationError, DomainError):
        return None


def _status(
    session: Session, user: User, match_id: int, settings: Settings
) -> tuple[ReportStatus, Path | None]:
    reader_match(session, user, match_id)
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == match_id,
            ProcessingJob.job_type == JobType.MATCH_REPORT,
            ProcessingJob.status.in_(
                (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
    )
    if job is None:
        return ReportStatus(available=False, current=False, stale=False), None
    artifact = _artifact(job, settings)
    current = (
        artifact is not None
        and job.report_snapshot
        == capture_inputs(session, user, match_id, settings).snapshot
    )
    return ReportStatus(
        available=artifact is not None,
        current=current,
        stale=not current,
        job_id=job.id,
        summary=artifact[1] if artifact else None,
    ), artifact[0] if current else None


def report_status(
    session: Session, user: User, match_id: int, settings: Settings
) -> ReportStatus:
    return _status(session, user, match_id, settings)[0]


def report_file(
    session: Session, user: User, match_id: int, settings: Settings
) -> Path:
    status, path = _status(session, user, match_id, settings)
    if path is None:
        raise DomainError(
            409,
            "Analytics have changed. Regenerate the report to include current results."
            if status.stale
            else "Generate a match report before downloading it.",
        )
    return path


def csv_cell(value: str | int | float | None) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        raise DomainError(
            409, "The analytics export contains an invalid numerical value."
        )
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(
    session: Session, user: User, match_id: int, settings: Settings, family: str
) -> str:
    inputs = capture_inputs(session, user, match_id, settings)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    if family == "players":
        rows = read_players(inputs)
        if rows is None:
            raise DomainError(
                409,
                "Current player analytics are unavailable. "
                "Generate current analytics before exporting.",
            )
        writer.writerow(PLAYER_COLUMNS)
        for row in rows:
            values = row.model_dump()
            values["effective_team"] = (
                team_label(inputs.assignments, row.track_id)
                if inputs.assignments is not None
                else None
            )
            writer.writerow([csv_cell(values[name]) for name in PLAYER_COLUMNS])
    elif family == "teams":
        if inputs.tactics is None:
            raise DomainError(
                409,
                "Current team tactical analytics are unavailable. "
                "Generate current analytics before exporting.",
            )
        writer.writerow(TEAM_COLUMNS)
        for row in team_analytics_service._summaries(inputs.tactics):
            values = row.model_dump()
            writer.writerow([csv_cell(values[name]) for name in TEAM_COLUMNS])
    else:
        raise ValueError("Unknown export family")
    # End the read transaction so the second guard sees concurrent changes.
    session.rollback()
    if capture_inputs(session, user, match_id, settings).snapshot != inputs.snapshot:
        raise DomainError(
            409, "Analytics changed during export. Refresh and try again."
        )
    return stream.getvalue()
