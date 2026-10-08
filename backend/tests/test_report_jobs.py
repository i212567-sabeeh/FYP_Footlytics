"""Reports consume saved inputs: queue, freshness, atomic publication and downloads."""

import csv
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import test_jobs
import test_team_analytics_jobs as previous
from conftest import TEST_PASSWORD, migration_config
from pypdf import PdfReader
from report_fixtures import saved_analytics
from sqlalchemy import select, text, update

from alembic import command
from app.auth.tokens import create_access_token
from app.database.session import create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.services.domain_common import DomainError
from app.services.report_artifacts import ReportArtifact, validate_pdf
from app.services.report_service import PLAYER_COLUMNS, TEAM_COLUMNS
from app.workers import match_report as worker
from app.workers.queue import RQJobQueue, get_job_queue

domain = previous.domain
source_video = previous.source_video
calibrated = previous.calibrated
detections = previous.detections
tracks = previous.tracks
coordinates = previous.coordinates
upstream_queue = previous.upstream_queue
trajectory_queue = previous.trajectory_queue
analytics_queue = previous.analytics_queue
tactical_queue = previous.queue
tactical_inputs = previous.tactical_inputs


class RecordingQueue(previous.RecordingQueue):
    def enqueue_match_report(self, job_id, attempt, rq_job_id):
        self.enqueue_player_analytics(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, settings, monkeypatch, tactical_queue):
    instance = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: instance
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    return instance


@pytest.fixture
def saved(tactical_inputs, session, settings, queue, monkeypatch):
    jobs = saved_analytics(session, settings, tactical_inputs)
    # All report work, including the smoke test, begins from these published files.
    monkeypatch.setattr(
        previous.worker,
        "calculate_teams",
        Mock(side_effect=AssertionError("Analytics recalculation")),
    )
    return tactical_inputs.match_id, jobs


def enqueue(client, match_id, headers):
    result = client.post(f"/api/matches/{match_id}/jobs/match-report", headers=headers)
    assert result.status_code == 202, result.text
    return result.json()


def get(client, match_id, headers, suffix="report"):
    return client.get(f"/api/matches/{match_id}/{suffix}", headers=headers)


def generate(client, match_id, headers, engine):
    job = enqueue(client, match_id, headers)
    worker.generate_report(job["id"], 0)
    return test_jobs.persisted_job(engine, job["id"])


def fingerprint(engine, settings):
    with engine.connect() as connection:
        rows = {
            name: [
                dict(row)
                for row in connection.execute(
                    text(f"SELECT * FROM {name} ORDER BY id")
                ).mappings()
            ]
            for name in ("matches", "track_team_assignments", "pitch_calibrations")
        }
        rows["processing_jobs"] = [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT * FROM processing_jobs "
                    "WHERE job_type != 'match_report' ORDER BY id"
                )
            ).mappings()
        ]
    files = {
        str(path.relative_to(settings.storage_dir)): path.read_bytes()
        for path in settings.storage_dir.rglob("*")
        if path.is_file() and "reports" not in path.parts
    }
    return rows, files


def test_synthetic_smoke_saved_inputs_pdf_csv_and_consumer_independence(
    client, saved, engine, settings, coach_headers, queue, monkeypatch, record_property
):
    match_id, _ = saved
    before = fingerprint(engine, settings)
    progress = Mock(wraps=worker._running)
    monkeypatch.setattr(worker, "_running", progress)
    job = generate(client, match_id, coach_headers, engine)
    assert job.status == "completed" and job.progress_percent == 100
    assert queue.calls[-1][:2] == (job.id, 0)
    path = settings.storage_dir / job.artifact_relative_path
    pages, size = validate_pdf(path)
    assert pages >= 8 and size > 1000
    status = get(client, match_id, coach_headers)
    assert status.json()["current"] and not status.json()["stale"]
    pdf = get(client, match_id, coach_headers, "report/file")
    assert pdf.status_code == 200 and pdf.content == path.read_bytes()
    assert pdf.headers["content-type"] == "application/pdf"
    assert (
        f"footlytics-match-{match_id}-report.pdf" in pdf.headers["content-disposition"]
    )
    assert (
        pdf.headers["cache-control"] == "no-store"
        and pdf.headers["x-content-type-options"] == "nosniff"
    )
    text_content = " ".join(
        page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert "Track 9" in text_content and "Unknown: 1" in text_content
    assert str(settings.storage_dir) not in text_content
    exported = {}
    exported_text = {}
    for family, columns, count in (
        ("player", PLAYER_COLUMNS, 7),
        ("team", TEAM_COLUMNS, 2),
    ):
        response = get(
            client, match_id, coach_headers, f"exports/{family}-analytics.csv"
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        assert (
            f"footlytics-match-{match_id}-{family}-analytics.csv"
            in response.headers["content-disposition"]
        )
        parsed = csv.DictReader(io.StringIO(response.text))
        assert parsed.fieldnames == columns
        rows = list(parsed)
        assert len(rows) == count
        exported[family] = rows
        exported_text[family] = response.text
    assert exported["player"][5]["effective_team"] == "Team B"  # Manual override.
    assert exported["player"][6]["effective_team"] == "Unknown"
    assert exported["player"][0]["average_speed_kmh"] == "36.0"
    assert exported["team"][0]["avg_width_metres"] == "3.0"
    assert exported["team"][0]["avg_depth_metres"] == "4.0"
    assert exported["team"][0]["avg_centroid_distance_to_opponent_metres"] == ""
    assert fingerprint(engine, settings) == before
    assert not list(settings.storage_dir.rglob("*.partial"))
    public = client.get(f"/api/jobs/{job.id}", headers=coach_headers).json()
    for field in ("artifact_relative_path", "report_snapshot", "artifact_version"):
        assert field not in json.dumps(public) and field not in status.text
    percentages = [
        c.kwargs["progress_percent"]
        for c in progress.call_args_list
        if "progress_percent" in c.kwargs
    ]
    assert percentages == sorted(percentages) and percentages[-1] == 100
    result = {
        "size_bytes": size,
        "page_count": pages,
        "sections": job.report_summary["sections"],
        "player_rows": 7,
        "team_rows": 2,
        "player_csv_columns": len(PLAYER_COLUMNS),
        "team_csv_columns": len(TEAM_COLUMNS),
        "csv_headers": {"player": PLAYER_COLUMNS, "team": TEAM_COLUMNS},
        "csv_examples": {name: rows[0] for name, rows in exported.items()},
        "heatmaps": job.report_summary["heatmaps"],
        "title": PdfReader(io.BytesIO(pdf.content)).metadata.title,
    }
    record_property("report_smoke", json.dumps(result))
    # Retain a reviewable synthetic artifact outside runtime source control.
    review = Path(__file__).resolve().parents[2] / ".tools/phase14-review"
    review.mkdir(parents=True, exist_ok=True)
    (review / "match-report.pdf").write_bytes(pdf.content)
    for family, content in exported_text.items():
        (review / f"{family}-analytics.csv").write_text(content, encoding="utf-8")
    (review / "smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    "dependency",
    [
        "metadata",
        "team_name",
        "assignments",
        "player_result",
        "team_result",
        "player_file",
        "team_file",
        "video",
        "calibration",
    ],
)
def test_dependencies_make_previous_report_stale(
    client, saved, engine, settings, coach_headers, session, dependency
):
    match_id, analytics = saved
    report = generate(client, match_id, coach_headers, engine)
    original = (settings.storage_dir / report.artifact_relative_path).read_bytes()
    match = session.get(Match, match_id)
    if dependency == "metadata":
        match.title += " revised"
    elif dependency == "team_name":
        match.team_a.name += " revised"
    elif dependency == "assignments":
        session.scalar(
            select(TrackTeamAssignment).where(TrackTeamAssignment.track_id == 1)
        ).manual_team = "team_b"
    elif dependency in ("player_result", "team_result"):
        analytics[0 if dependency == "player_result" else 1].attempt += 1
    elif dependency.endswith("file"):
        index = 0 if dependency == "player_file" else 1
        filename = "players.csv" if index == 0 else "team_tactics_summary.csv"
        path = settings.storage_dir / analytics[index].artifact_relative_path / filename
        path.write_bytes(path.read_bytes() + b"\n")
    elif dependency == "video":
        from app.models.media import MatchVideo

        session.scalar(
            select(MatchVideo).where(MatchVideo.match_id == match_id)
        ).is_active = False
    else:
        from app.models.calibration import PitchCalibration

        session.scalar(
            select(PitchCalibration).where(PitchCalibration.match_id == match_id)
        ).pitch_length_metres += 1
    session.commit()
    status = get(client, match_id, coach_headers).json()
    assert status["stale"] and not status["current"] and status["available"]
    assert get(client, match_id, coach_headers, "report/file").status_code == 409
    assert (
        settings.storage_dir / report.artifact_relative_path
    ).read_bytes() == original


@pytest.mark.parametrize("missing", [0, 1, "both"])
def test_partial_reports_and_unavailable_exports(
    client, saved, engine, settings, coach_headers, session, missing
):
    match_id, jobs = saved
    for index, job in enumerate(jobs):
        if missing in (index, "both"):
            job.status = "failed"
    session.commit()
    job = generate(client, match_id, coach_headers, engine)
    assert job.status == "completed_with_warnings"
    assert get(client, match_id, coach_headers).json()["current"]
    text_content = " ".join(
        page.extract_text()
        for page in PdfReader(settings.storage_dir / job.artifact_relative_path).pages
    )
    assert "Unavailable" in text_content
    for index, family in enumerate(("player", "team")):
        assert get(
            client, match_id, coach_headers, f"exports/{family}-analytics.csv"
        ).status_code == (409 if missing in (index, "both") else 200)


@pytest.mark.parametrize(
    "fault",
    ["loading", "builder", "validation", "publish", "completion", "inputs", "corrupt"],
)
def test_failure_and_retry_preserve_previous_pdf(
    client, saved, engine, settings, coach_headers, monkeypatch, fault
):
    match_id, _ = saved
    previous_report = generate(client, match_id, coach_headers, engine)
    original_path = settings.storage_dir / previous_report.artifact_relative_path
    original = original_path.read_bytes()
    job = enqueue(client, match_id, coach_headers)
    assert get(client, match_id, coach_headers, "report/file").content == original
    with monkeypatch.context() as patch:
        if fault == "loading":
            patch.setattr(
                worker, "load_report_data", Mock(side_effect=OSError("private input"))
            )
        elif fault in ("builder", "validation", "publish"):
            target, attribute = (
                (ReportArtifact, "publish")
                if fault == "publish"
                else (worker, "build_report" if fault == "builder" else "validate_pdf")
            )
            patch.setattr(
                target,
                attribute,
                Mock(side_effect=OSError("/private/storage/password")),
            )
        elif fault == "corrupt":
            patch.setattr(
                worker, "build_report", lambda data, path: path.write_bytes(b"corrupt")
            )
        elif fault == "completion":
            original_running = worker._running

            def complete(*args, **kwargs):
                if kwargs.get("status") == "completed":
                    raise RuntimeError("private database failure")
                return original_running(*args, **kwargs)

            patch.setattr(worker, "_running", complete)
        else:
            original_build = worker.build_report

            def change(data, path):
                with create_session_factory(engine)() as other:
                    other.execute(
                        update(Match)
                        .where(Match.id == match_id)
                        .values(title="Changed while building")
                    )
                    other.commit()
                return original_build(data, path)

            patch.setattr(worker, "build_report", change)
        for attempt in (0, 1):
            if attempt:
                assert (
                    client.post(
                        f"/api/jobs/{job['id']}/retry", headers=coach_headers
                    ).status_code
                    == 202
                )
            with pytest.raises((OSError, RuntimeError, ValueError, DomainError)):
                worker.generate_report(job["id"], attempt)
            failed = test_jobs.persisted_job(engine, job["id"])
            assert failed.status == "failed" and failed.artifact_relative_path is None
            assert "private" not in failed.error_message
            # For the second 'inputs' attempt make the mutation differ again.
            if fault == "inputs":
                with create_session_factory(engine)() as other:
                    other.execute(
                        update(Match)
                        .where(Match.id == match_id)
                        .values(title="Between retries")
                    )
                    other.commit()
    assert original_path.read_bytes() == original
    assert list((settings.storage_dir / "reports").rglob("*.pdf")) == [original_path]
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert get(client, match_id, coach_headers).json()["current"] == (fault != "inputs")
    # A fresh retry can succeed, while an obsolete attempt cannot replace it.
    assert (
        client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers).status_code
        == 202
    )
    worker.generate_report(job["id"], 1)
    assert test_jobs.persisted_job(engine, job["id"]).status == "queued"
    worker.generate_report(job["id"], 2)
    assert get(client, match_id, coach_headers).json()["current"]


@pytest.mark.parametrize(
    "role,read,write",
    [
        ("admin", 200, 202),
        ("coach", 200, 202),
        ("analyst", 200, 202),
        ("club_management", 200, 403),
        ("player", 403, 403),
    ],
)
def test_report_and_csv_roles(
    client, saved, engine, settings, coach_headers, domain, role, read, write
):
    match_id, _ = saved
    generate(client, match_id, coach_headers, engine)
    account = domain["post"](
        "users",
        {
            "email": f"report-{role}@example.com",
            "full_name": role,
            "password": TEST_PASSWORD,
            "roles": [role],
        },
    )
    if role != "admin":
        domain["post"](
            f"clubs/{domain['clubs'][0]['id']}/members", {"user_id": account["id"]}
        )
    headers = {
        "Authorization": f"Bearer {create_access_token(account['id'], settings)}"
    }
    for suffix in (
        "report",
        "report/file",
        "exports/player-analytics.csv",
        "exports/team-analytics.csv",
    ):
        response = get(client, match_id, headers, suffix)
        assert response.status_code == read, response.text
    assert (
        client.post(
            f"/api/matches/{match_id}/jobs/match-report", headers=headers
        ).status_code
        == write
    )


def test_cross_club_anonymous_no_video_and_missing_report(
    client, domain, coach_headers, queue
):
    for headers, status in ((coach_headers, 404), ({}, 401)):
        match_id = domain["matches"][1]["id"]
        for suffix in (
            "report",
            "report/file",
            "exports/player-analytics.csv",
            "exports/team-analytics.csv",
        ):
            assert get(client, match_id, headers, suffix).status_code == status
        assert (
            client.post(
                f"/api/matches/{match_id}/jobs/match-report", headers=headers
            ).status_code
            == status
        )
    match_id = domain["matches"][0]["id"]
    assert not get(client, match_id, coach_headers).json()["available"]
    assert get(client, match_id, coach_headers, "report/file").status_code == 409
    assert (
        client.post(
            f"/api/matches/{match_id}/jobs/match-report", headers=coach_headers
        ).status_code
        == 409
    )
    assert not queue.calls


def test_queue_failure_is_safe_no_sync_duplicate_delivery(
    client, saved, coach_headers, engine, queue, monkeypatch
):
    match_id, _ = saved
    job = enqueue(client, match_id, coach_headers)
    assert (
        client.post(
            f"/api/matches/{match_id}/jobs/match-report", headers=coach_headers
        ).status_code
        == 409
    )
    test_jobs.fail_job(engine, job["id"])
    monkeypatch.setattr(
        queue,
        "enqueue_match_report",
        Mock(side_effect=OSError("private redis password")),
    )
    response = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert response.status_code == 503 and "private" not in response.text
    worker.generate_report(job["id"], 0)
    failed = test_jobs.persisted_job(engine, job["id"])
    assert failed.status == "failed" and failed.artifact_relative_path is None


@pytest.mark.parametrize(
    "unsafe",
    ["../secret.pdf", "C:/secret.pdf", "reports/matches/99/secret.pdf", "missing"],
)
def test_untrusted_artifact_paths_never_downloaded(
    client, saved, coach_headers, engine, session, unsafe
):
    match_id, _ = saved
    report = generate(client, match_id, coach_headers, engine)
    session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == report.id)
        .values(artifact_relative_path=unsafe)
    )
    session.commit()
    response = get(client, match_id, coach_headers, "report/file")
    assert response.status_code == 409 and unsafe not in response.text


def test_rq_report_payload_ids_only(settings):
    queue = RQJobQueue(settings)
    queue.queue = Mock()
    queue.enqueue_match_report(42, 3, "report-attempt")
    args, kwargs = queue.queue.enqueue.call_args
    assert args == ("app.workers.match_report.generate_report",)
    assert kwargs["kwargs"] == {"processing_job_id": 42, "attempt": 3}
    assert kwargs["job_id"] == "report-attempt" and kwargs["unique"]
    queue.close()


def test_populated_0011_upgrade_preserves_every_table_and_manual_overrides(
    saved, engine
):
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0011_team_tactical_analytics")
        from sqlalchemy import inspect

        tables = [
            name
            for name in inspect(connection).get_table_names()
            if name != "alembic_version"
        ]
        before = {
            name: [
                dict(row)
                for row in connection.execute(
                    text(f'SELECT * FROM "{name}"')
                ).mappings()
            ]
            for name in tables
        }
        assert any(row["manual_team"] for row in before["track_team_assignments"])
        kinds = {row["job_type"] for row in before["processing_jobs"]}
        assert {
            "player_detection",
            "player_tracking",
            "coordinate_mapping",
            "trajectory_cleaning",
            "player_analytics",
            "team_tactical_analytics",
        } <= kinds
        command.upgrade(config, "head")
        for name, original in before.items():
            after = [
                dict(row)
                for row in connection.execute(
                    text(f'SELECT * FROM "{name}"')
                ).mappings()
            ]
            assert (
                [{key: row[key] for key in original[0]} for row in after] == original
                if original
                else not after
            )
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0015_team_color_prototypes"
        )
        assert not connection.execute(text("PRAGMA foreign_key_check")).all()
        command.check(config)


def test_downgrade_refuses_report_history(client, saved, coach_headers, engine):
    enqueue(client, saved[0], coach_headers)
    with (
        engine.begin() as connection,
        pytest.raises(RuntimeError, match="match report jobs"),
    ):
        command.downgrade(migration_config(connection), "0011_team_tactical_analytics")


@pytest.mark.parametrize("family", [0, 1])
def test_unavailable_family_becoming_current_makes_report_stale(
    client, saved, coach_headers, engine, session, family
):
    match_id, analytics = saved
    analytics[family].status = "failed"
    session.commit()
    generate(client, match_id, coach_headers, engine)
    assert get(client, match_id, coach_headers).json()["current"]
    analytics[family].status = "completed"
    session.commit()
    assert get(client, match_id, coach_headers).json()["stale"]
    generate(client, match_id, coach_headers, engine)
    assert get(client, match_id, coach_headers).json()["current"]


def test_irrelevant_changes_do_not_stale_report(
    client, saved, coach_headers, engine, session
):
    match_id, analytics = saved
    generate(client, match_id, coach_headers, engine)
    row = session.scalar(
        select(TrackTeamAssignment).where(
            TrackTeamAssignment.match_id == match_id, TrackTeamAssignment.track_id == 6
        )
    )
    assert row.manual_team == "team_b"
    row.automatic_team = "unknown"  # Masked by the same effective manual label.
    row.automatic_confidence = 0.1
    analytics[0].warning_message = "Operational warning not rendered in the PDF"
    analytics[0].rq_job_id = "irrelevant-queue-metadata"
    session.commit()
    assert get(client, match_id, coach_headers).json()["current"]


def test_player_csv_nulls_stay_blank_and_missing_assignments_are_unavailable(
    client, saved, coach_headers, settings, session
):
    from report_fixtures import player

    from app.services.tracking_inputs import file_version

    match_id, analytics = saved
    job = analytics[0]
    path = settings.storage_dir / job.artifact_relative_path / "players.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    rows[0] = player(1, True).model_dump()
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = json.loads(json.dumps(job.analytics_summary))
    summary["artifact_versions"]["players"] = file_version(path)
    job.analytics_summary = summary
    for row in session.scalars(select(TrackTeamAssignment)):
        session.delete(row)
    session.commit()
    response = get(client, match_id, coach_headers, "exports/player-analytics.csv")
    assert response.status_code == 200, response.text
    row = next(csv.DictReader(io.StringIO(response.text)))
    for name in (
        "average_speed_mps",
        "average_speed_kmh",
        "max_speed_mps",
        "max_speed_kmh",
        "effective_team",
    ):
        assert row[name] == ""
    assert not {"nan", "inf", "None"} & set(row.values())


def test_duplicate_completed_delivery_does_not_rebuild(
    client, saved, coach_headers, engine, monkeypatch
):
    job = generate(client, saved[0], coach_headers, engine)
    builder = Mock(side_effect=AssertionError("Duplicate report render"))
    monkeypatch.setattr(worker, "build_report", builder)
    worker.generate_report(job.id, 0)
    builder.assert_not_called()
