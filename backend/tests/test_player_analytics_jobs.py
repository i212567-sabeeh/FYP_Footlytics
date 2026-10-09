"""Saved-trajectory jobs, atomic bundles, provenance, authorization and API reload."""

import csv
import json
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import test_coordinate_jobs
import test_jobs
import test_trajectory_jobs
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import inspect, text, update
from sqlalchemy.exc import IntegrityError
from test_player_analytics import point, provenance

from alembic import command
from app.analytics.trajectory_rows import AnalyticsError
from app.auth.tokens import create_access_token
from app.cv import trajectory_pipeline
from app.cv.coordinate_rows import CoordinateObservation
from app.cv.trajectory import TrajectoryObservation
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.services.analytics_artifacts import MODELS, AnalyticsArtifacts, read_rows
from app.services.coordinate_artifacts import COLUMNS as COORDINATE_COLUMNS
from app.services.coordinate_inputs import current_mapping_inputs
from app.services.coordinate_service import current_coordinates
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS
from app.services.domain_common import DomainError
from app.services.tracking_artifacts import COLUMNS as TRACK_COLUMNS
from app.services.tracking_inputs import current_detection, file_version
from app.services.trajectory_artifacts import TrajectoryArtifact
from app.workers import player_analytics as worker
from app.workers.queue import RQJobQueue, get_job_queue

domain = test_trajectory_jobs.domain
source_video = test_trajectory_jobs.source_video
calibrated = test_trajectory_jobs.calibrated
detections = test_trajectory_jobs.detections
tracks = test_trajectory_jobs.tracks
coordinates = test_trajectory_jobs.coordinates
upstream_queue = test_trajectory_jobs.upstream_queue
trajectory_queue = test_trajectory_jobs.queue


class RecordingQueue(test_trajectory_jobs.RecordingQueue):
    def enqueue_player_analytics(self, job_id, attempt, rq_job_id):
        self.enqueue_trajectory_cleaning(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, settings, monkeypatch, trajectory_queue):
    instance = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: instance
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(
        trajectory_pipeline,
        "clean_coordinates",
        Mock(side_effect=AssertionError("Cleaning rerun")),
    )
    return instance


def publish_trajectories(session, settings, coordinates, points):
    source = current_coordinates(
        session, session.get(Match, coordinates.match_id), settings
    )
    job = ProcessingJob(
        match_id=coordinates.match_id,
        video_id=coordinates.video_id,
        job_type="trajectory_cleaning",
        status="completed",
        progress_percent=100,
        current_stage="completed",
        created_by_user_id=coordinates.created_by_user_id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        coordinate_snapshot=source.version,
    )
    session.add(job)
    session.flush()
    summary = provenance(points, length=30, width=20, coordinate_job_id=coordinates.id)
    with TrajectoryArtifact(
        settings, job.match_id, job.video_id, job.id, 0
    ) as artifact:
        previous_segment = None
        for i, p in enumerate(points, 1):
            x, y = p.clean if p.clean is not None else (-1, 0)
            px, py = (x + 10) * 2, y * 2
            raw = CoordinateObservation(
                i,
                p.frame,
                p.timestamp,
                p.track_id,
                (px - 1, py - 1, px + 1, py),
                0.9,
                (px, py),
                (x, y),
                p.clean is not None,
            )
            status = (
                "outside_pitch"
                if p.clean is None
                else "segment_start"
                if (p.track_id, p.segment_id) != previous_segment
                else "accepted"
            )
            if p.clean is not None:
                previous_segment = (p.track_id, p.segment_id)
            artifact.write_observation(
                TrajectoryObservation(
                    raw,
                    p.segment_id,
                    p.clean,
                    status,
                )
            )
        job.artifact_relative_path = artifact.publish()
        job.trajectory_summary = {
            **summary.model_dump(mode="json"),
            "artifact_version": file_version(artifact.path),
        }
        session.commit()
        artifact.keep()
    return job


@pytest.fixture
def trajectories(coordinates, settings, session):
    rows = test_coordinate_jobs.rows_at(
        settings.storage_dir / coordinates.artifact_relative_path
    )
    points = [
        point(
            float(r["timestamp_seconds"]),
            float(r["pitch_x"]) if r["inside_pitch"] == "true" else None,
            float(r["pitch_y"]),
            track=int(r["track_id"]),
            frame=int(r["frame_number"]),
        )
        for r in rows
    ]
    points.sort(key=lambda p: (p.track_id, p.timestamp, p.frame))
    return publish_trajectories(session, settings, coordinates, points)


def enqueue(client, match_id, headers):
    response = client.post(
        f"/api/matches/{match_id}/jobs/player-analytics", headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def result(client, match_id, headers, suffix=""):
    return client.get(
        f"/api/matches/{match_id}/player-analytics{suffix}", headers=headers
    )


def bundles(settings):
    return list((settings.storage_dir / "analytics").rglob("attempt-*"))


def test_worker_persists_bundle_progress_pagination_and_private_api(
    client,
    trajectories,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    source_path = settings.storage_dir / trajectories.artifact_relative_path
    original = source_path.read_bytes()
    job = enqueue(client, trajectories.match_id, coach_headers)
    assert job["analytics_summary"] is None and job["job_type"] == "player_analytics"
    assert queue.calls[0][:2] == (job["id"], 0)
    assert result(client, trajectories.match_id, coach_headers).status_code == 409
    state = Mock(wraps=worker._running)
    monkeypatch.setattr(worker, "_running", state)
    worker.analyze_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed" and stored.progress_percent == 100
    path = settings.storage_dir / stored.artifact_relative_path
    assert {p.name for p in path.iterdir()} == {f"{name}.csv" for name in MODELS}
    assert not list(settings.storage_dir.rglob("*.partial"))
    # Track 7's 0.1 s and 0.2 s steps form one 0.3 s speed-window measurement.
    assert stored.analytics_summary["valid_intervals"] == 1
    assert stored.analytics_summary["speed_window_seconds"] == 0.2
    assert stored.analytics_summary["method"] == "minimum_time_windows_v2"
    assert stored.analytics_summary["unique_tracks"] == 2
    assert [
        call.kwargs["progress_percent"]
        for call in state.call_args_list
        if "progress_percent" in call.kwargs
    ] == [49, 99, 100]
    response = result(client, trajectories.match_id, coach_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2 and [r["track_id"] for r in data["items"]] == [3, 7]
    assert {r["speed_window_seconds"] for r in data["items"]} == {0.2}
    assert data["items"][0]["average_speed_mps"] is None
    assert data["items"][1]["average_speed_mps"] == 0
    assert data["items"][1]["active_duration_seconds"] == pytest.approx(0.3)
    page = result(
        client, trajectories.match_id, coach_headers, "?offset=1&limit=1"
    ).json()
    assert page["total"] == 2 and [r["track_id"] for r in page["items"]] == [7]
    assert (
        result(client, trajectories.match_id, coach_headers, "?offset=2").json()[
            "items"
        ]
        == []
    )
    for track_id in (3, 7):
        detail = result(client, trajectories.match_id, coach_headers, f"/{track_id}")
        assert detail.status_code == 200
        heatmap = result(
            client, trajectories.match_id, coach_headers, f"/{track_id}/heatmap"
        )
        assert heatmap.status_code == 200
        body = heatmap.json()
        assert body["video_duration_seconds"] > 0
        assert body["observed_coverage_percent"] == pytest.approx(
            100 * body["total_occupancy_seconds"] / body["video_duration_seconds"]
        )
        assert body["coverage_warning"]
        assert (
            detail.json()["observed_coverage_percent"]
            == body["observed_coverage_percent"]
        )
        assert heatmap.json()["total_occupancy_seconds"] == (
            0 if track_id == 3 else pytest.approx(0.3)
        )
        assert (
            heatmap.json()["pitch_length_metres"],
            heatmap.json()["pitch_width_metres"],
        ) == (30, 20)
    for suffix in ("/999", "/999/heatmap"):
        assert (
            result(client, trajectories.match_id, coach_headers, suffix).status_code
            == 404
        )
    public = client.get(f"/api/jobs/{job['id']}", headers=coach_headers)
    assert "artifact_versions" not in public.json()["analytics_summary"]
    for text_value in (public.text, response.text, heatmap.text):
        assert (
            "artifact_relative_path" not in text_value
            and "trajectory_snapshot" not in text_value
        )
        assert (
            str(settings.storage_dir) not in text_value
            and "analytics/matches/" not in text_value
        )
    assert source_path.read_bytes() == original
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    worker.analyze_players(job["id"], 0)
    assert before == {p.name: p.read_bytes() for p in path.iterdir()}


@pytest.mark.parametrize("coordinates", ["empty", "outside", "inside"], indirect=True)
def test_empty_all_rejected_and_stationary_inputs(
    client, trajectories, settings, engine, coach_headers, queue, coordinates
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    worker.analyze_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    data = result(client, trajectories.match_id, coach_headers).json()
    assert all(row["total_distance_metres"] == 0 for row in data["items"])
    if not trajectories.trajectory_summary["usable_rows"]:
        assert stored.status == "completed_with_warnings"
        assert all(row["max_speed_mps"] is None for row in data["items"])
        assert not list(
            read_rows(
                settings.storage_dir / stored.artifact_relative_path / "heatmaps.csv",
                "heatmaps",
            )
        )


def test_missing_trajectory_result_rejected(client, coordinates, coach_headers, queue):
    response = client.post(
        f"/api/matches/{coordinates.match_id}/jobs/player-analytics",
        headers=coach_headers,
    )
    assert response.status_code == 409 and "trajectory" in response.text
    assert not queue.calls


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "empty",
        "summary",
        "video",
        "calibration",
        "tracking",
        "coordinates",
        "trajectory",
    ],
)
def test_invalid_inputs_rejected_before_queue(
    client,
    trajectories,
    coordinates,
    tracks,
    calibrated,
    source_video,
    settings,
    session,
    coach_headers,
    queue,
    fault,
):
    if fault == "missing":
        (settings.storage_dir / trajectories.artifact_relative_path).unlink()
    elif fault == "empty":
        (settings.storage_dir / trajectories.artifact_relative_path).write_text("")
    elif fault == "summary":
        trajectories.trajectory_summary = {
            **trajectories.trajectory_summary,
            "usable_rows": 999,
        }
    elif fault == "video":
        source_video[0].is_active = False
    elif fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "trajectory":
        trajectories.coordinate_snapshot = {}
    else:
        target = tracks if fault == "tracking" else coordinates
        target.updated_at = utc_now()
    session.commit()
    response = client.post(
        f"/api/matches/{trajectories.match_id}/jobs/player-analytics",
        headers=coach_headers,
    )
    assert response.status_code == 409 and not queue.calls


@pytest.mark.parametrize(
    "fault",
    [
        "video",
        "calibration",
        "tracking",
        "coordinates",
        "trajectory",
        "new_trajectory",
        "file",
    ],
)
def test_changes_during_processing_prevent_publication(
    client,
    trajectories,
    coordinates,
    tracks,
    calibrated,
    source_video,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
    fault,
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    actual = AnalyticsArtifacts.write
    changed = False

    def mutate(artifact, name, row):
        nonlocal changed
        actual(artifact, name, row)
        if changed:
            return
        changed = True
        with create_session_factory(engine)() as session:
            if fault == "video":
                session.execute(
                    update(MatchVideo)
                    .where(MatchVideo.id == source_video[0].id)
                    .values(is_active=False)
                )
            elif fault == "calibration":
                session.execute(
                    update(PitchCalibration)
                    .where(PitchCalibration.id == calibrated.id)
                    .values(updated_at=utc_now())
                )
            elif fault == "file":
                path = settings.storage_dir / trajectories.artifact_relative_path
                path.write_bytes(path.read_bytes() + b"\n")
            elif fault == "new_trajectory":
                old = session.get(ProcessingJob, trajectories.id)
                newer = ProcessingJob(
                    match_id=old.match_id,
                    video_id=old.video_id,
                    job_type="trajectory_cleaning",
                    status="completed",
                    progress_percent=100,
                    current_stage="completed",
                    created_by_user_id=old.created_by_user_id,
                    attempt=0,
                    retry_count=0,
                    finished_at=utc_now(),
                    coordinate_snapshot=old.coordinate_snapshot,
                )
                session.add(newer)
                session.flush()
                relative = old.artifact_relative_path.replace(
                    f"/jobs/{old.id}/", f"/jobs/{newer.id}/"
                )
                path = settings.storage_dir / relative
                path.parent.mkdir(parents=True)
                path.write_bytes(
                    (settings.storage_dir / old.artifact_relative_path).read_bytes()
                )
                newer.artifact_relative_path = relative
                newer.trajectory_summary = {
                    **old.trajectory_summary,
                    "artifact_version": file_version(path),
                }
            else:
                identity = {
                    "tracking": tracks.id,
                    "coordinates": coordinates.id,
                    "trajectory": trajectories.id,
                }[fault]
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == identity)
                    .values(updated_at=utc_now())
                )
            session.commit()

    monkeypatch.setattr(AnalyticsArtifacts, "write", mutate)
    publish = Mock(wraps=AnalyticsArtifacts.publish)
    monkeypatch.setattr(AnalyticsArtifacts, "publish", publish)
    with pytest.raises((DomainError, AnalyticsError)):
        worker.analyze_players(job["id"], 0)
    publish.assert_not_called()
    stored = test_jobs.persisted_job(engine, job["id"])
    assert (
        stored.status == "failed"
        and stored.artifact_relative_path is None
        and stored.analytics_summary is None
    )
    assert (
        not bundles(settings) and str(settings.storage_dir) not in stored.error_message
    )


def test_team_assignment_during_analytics_does_not_invalidate(
    client,
    trajectories,
    tracks,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    actual = AnalyticsArtifacts.write
    changed = False

    def correct_team(artifact, name, row):
        nonlocal changed
        actual(artifact, name, row)
        if not changed:
            changed = True
            with create_session_factory(engine)() as session:
                session.add(
                    TrackTeamAssignment(
                        match_id=tracks.match_id,
                        tracking_job_id=tracks.id,
                        tracking_version="a" * 64,
                        track_id=3,
                        automatic_team="unknown",
                        automatic_confidence=0,
                        manual_team="team_b",
                    )
                )
                session.commit()

    monkeypatch.setattr(AnalyticsArtifacts, "write", correct_team)
    worker.analyze_players(job["id"], 0)
    assert result(client, trajectories.match_id, coach_headers).status_code == 200
    with create_session_factory(engine)() as session:
        session.execute(update(TrackTeamAssignment).values(manual_team="team_a"))
        session.commit()
    assert (
        result(client, trajectories.match_id, coach_headers, "/7/heatmap").status_code
        == 200
    )


@pytest.mark.parametrize("fault", ["write", "publish", "commit"])
def test_failure_and_failed_retry_preserve_previous_complete_bundle(
    client,
    trajectories,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
    fault,
):
    first = enqueue(client, trajectories.match_id, coach_headers)
    worker.analyze_players(first["id"], 0)
    old = test_jobs.persisted_job(engine, first["id"])
    old_path = settings.storage_dir / old.artifact_relative_path
    original = {p.name: p.read_bytes() for p in old_path.iterdir()}
    second = enqueue(client, trajectories.match_id, coach_headers)
    real_publish, real_write, real_running = (
        AnalyticsArtifacts.publish,
        AnalyticsArtifacts.write,
        worker._running,
    )

    def fail_publish(artifact):
        real_publish(artifact)
        raise OSError("/private/analytics/storage")

    def fail_write(artifact, name, row):
        real_write(artifact, name, row)
        raise OSError("/private/analytics/storage")

    def fail_commit(session, job_id, attempt, **values):
        if values.get("status") in ("completed", "completed_with_warnings"):
            raise OSError("/private/analytics/storage")
        return real_running(session, job_id, attempt, **values)

    for attempt in (0, 1):
        with monkeypatch.context() as patch:
            if fault == "write":
                patch.setattr(AnalyticsArtifacts, "write", fail_write)
            elif fault == "publish":
                patch.setattr(AnalyticsArtifacts, "publish", fail_publish)
            else:
                patch.setattr(worker, "_running", fail_commit)
            with pytest.raises(OSError):
                worker.analyze_players(second["id"], attempt)
        failed = test_jobs.persisted_job(engine, second["id"])
        assert failed.status == "failed" and "/private" not in failed.error_message
        assert (
            failed.artifact_relative_path is None and failed.analytics_summary is None
        )
        assert bundles(settings) == [old_path]
        assert original == {p.name: p.read_bytes() for p in old_path.iterdir()}
        assert (
            result(client, trajectories.match_id, coach_headers).json()["items"][0][
                "job_id"
            ]
            == first["id"]
        )
        assert (
            client.post(
                f"/api/jobs/{second['id']}/retry", headers=coach_headers
            ).status_code
            == 202
        )
        worker.analyze_players(second["id"], attempt)
        assert test_jobs.persisted_job(engine, second["id"]).status == "queued"
    worker.analyze_players(second["id"], 2)
    latest = test_jobs.persisted_job(engine, second["id"])
    assert "/attempt-2-" in latest.artifact_relative_path
    assert (
        result(client, trajectories.match_id, coach_headers).json()["items"][0][
            "job_id"
        ]
        == second["id"]
    )
    assert len(bundles(settings)) == 2


def test_publication_is_one_rename_and_source_rechecked_after_it(
    client,
    trajectories,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    real_publish = AnalyticsArtifacts.publish

    def change_during_publication(artifact):
        assert not artifact.path.exists()
        assert {p.name for p in artifact.temporary.iterdir()} == {
            f"{name}.csv" for name in MODELS
        }
        relative = real_publish(artifact)
        assert not artifact.temporary.exists()
        assert {p.name for p in artifact.path.iterdir()} == {
            f"{name}.csv" for name in MODELS
        }
        path = settings.storage_dir / trajectories.artifact_relative_path
        path.write_bytes(path.read_bytes() + b"\n")
        return relative

    monkeypatch.setattr(AnalyticsArtifacts, "publish", change_during_publication)
    with pytest.raises(DomainError):
        worker.analyze_players(job["id"], 0)
    assert not bundles(settings)
    assert test_jobs.persisted_job(engine, job["id"]).status == "failed"


def test_superseded_attempt_cannot_publish(
    client, trajectories, settings, engine, coach_headers, queue, monkeypatch
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    actual = AnalyticsArtifacts.write
    changed = False

    def supersede(artifact, name, row):
        nonlocal changed
        actual(artifact, name, row)
        if not changed:
            changed = True
            with create_session_factory(engine)() as session:
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == job["id"])
                    .values(attempt=1, status="queued")
                )
                session.commit()

    monkeypatch.setattr(AnalyticsArtifacts, "write", supersede)
    worker.analyze_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert (
        stored.status == "queued"
        and stored.attempt == 1
        and stored.artifact_relative_path is None
    )
    assert not bundles(settings)


@pytest.mark.parametrize(
    "fault",
    [
        "trajectory",
        "video",
        "calibration",
        "tracking",
        "coordinates",
        "players",
        "intervals",
        "sprints",
        "heatmaps",
        "summary",
        "path",
    ],
)
def test_stale_or_incomplete_bundles_are_not_current(
    client,
    trajectories,
    coordinates,
    tracks,
    calibrated,
    source_video,
    settings,
    session,
    coach_headers,
    queue,
    fault,
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    worker.analyze_players(job["id"], 0)
    stored = session.get(ProcessingJob, job["id"])
    if fault in MODELS:
        (settings.storage_dir / stored.artifact_relative_path / f"{fault}.csv").unlink()
    elif fault == "video":
        source_video[0].is_active = False
    elif fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "summary":
        stored.analytics_summary = {**stored.analytics_summary, "usable_rows": 99}
    elif fault == "path":
        stored.artifact_relative_path = "../../private"
    else:
        {"trajectory": trajectories, "coordinates": coordinates, "tracking": tracks}[
            fault
        ].updated_at = utc_now()
    session.commit()
    for suffix in ("", "/7", "/7/heatmap"):
        response = result(client, trajectories.match_id, coach_headers, suffix)
        assert response.status_code == 409 and "private" not in response.text


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
def test_role_permissions(
    client, trajectories, coach_headers, queue, domain, settings, role, read, write
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    worker.analyze_players(job["id"], 0)
    account = domain["post"](
        "users",
        {
            "email": f"analytics-{role}@example.com",
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
    for suffix in ("", "/7", "/7/heatmap"):
        assert (
            result(client, trajectories.match_id, headers, suffix).status_code == read
        )
    assert (
        client.post(
            f"/api/matches/{trajectories.match_id}/jobs/player-analytics",
            headers=headers,
        ).status_code
        == write
    )


def test_cross_club_and_anonymous_denied(client, domain, coach_headers, queue):
    match_id = domain["matches"][1]["id"]
    for headers, status in ((coach_headers, 404), ({}, 401)):
        for suffix in ("", "/7", "/7/heatmap"):
            assert result(client, match_id, headers, suffix).status_code == status
        assert (
            client.post(
                f"/api/matches/{match_id}/jobs/player-analytics", headers=headers
            ).status_code
            == status
        )
    assert not queue.calls


@pytest.mark.parametrize(
    "suffix",
    ["/0", "/-1", "/bad", f"/{2**63}", "/1.5/heatmap", "?limit=101", "?offset=-1"],
)
def test_invalid_api_parameters_rejected(client, domain, coach_headers, suffix):
    assert (
        result(client, domain["matches"][0]["id"], coach_headers, suffix).status_code
        == 422
    )


def test_queue_failure_and_active_job_protection(
    client, trajectories, engine, coach_headers, queue
):
    queue.unavailable = True
    assert (
        client.post(
            f"/api/matches/{trajectories.match_id}/jobs/player-analytics",
            headers=coach_headers,
        ).status_code
        == 503
    )
    queue.unavailable = False
    job = enqueue(client, trajectories.match_id, coach_headers)
    assert (
        client.post(
            f"/api/matches/{trajectories.match_id}/jobs/player-analytics",
            headers=coach_headers,
        ).status_code
        == 409
    )
    worker.analyze_players(job["id"], 0)
    assert test_jobs.persisted_job(engine, job["id"]).status == "completed"


def test_rq_receives_ids_and_attempt_only(settings, monkeypatch):
    queue = RQJobQueue(settings)
    persist = Mock(side_effect=lambda job, *_args, **_kwargs: job)
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_player_analytics(12, 3, "analytics-attempt")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.player_analytics.analyze_players",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert job.timeout == settings.detection_job_timeout_seconds
    queue.close()


def test_populated_0009_upgrade_preserves_all_results_and_overrides(
    engine, trajectories, coordinates, tracks, settings
):
    source = settings.storage_dir / trajectories.artifact_relative_path
    original_bytes = source.read_bytes()
    with create_session_factory(engine)() as session:
        session.add(
            TrackTeamAssignment(
                match_id=tracks.match_id,
                tracking_job_id=tracks.id,
                track_id=3,
                tracking_version="a" * 64,
                automatic_team="team_a",
                automatic_confidence=0.8,
                manual_team="team_b",
                updated_by_user_id=tracks.created_by_user_id,
            )
        )
        session.commit()
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0009_trajectory_cleaning")
        tables = (
            "users",
            "clubs",
            "teams",
            "matches",
            "match_videos",
            "processing_jobs",
            "pitch_calibrations",
            "track_team_assignments",
        )
        before = {
            name: connection.execute(text(f"SELECT * FROM {name} ORDER BY id"))
            .mappings()
            .all()
            for name in tables
        }
        assert all(before.values())
        assert any(row["coordinate_summary"] for row in before["processing_jobs"])
        assert any(row["trajectory_summary"] for row in before["processing_jobs"])
        command.upgrade(config, "0010_player_analytics")
        for name, original in before.items():
            current = (
                connection.execute(text(f"SELECT * FROM {name} ORDER BY id"))
                .mappings()
                .all()
            )
            assert [{k: row[k] for k in original[0]} for row in current] == original, (
                name
            )
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0010_player_analytics"
        )
        assert {"analytics_summary", "trajectory_snapshot"} <= {
            c["name"] for c in inspect(connection).get_columns("processing_jobs")
        }
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        command.upgrade(config, "head")
        command.check(config)
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE track_team_assignments SET tracking_job_id = 999999")
            )
    assert source.read_bytes() == original_bytes


def test_downgrade_cannot_destroy_analytics_history(
    client, trajectories, engine, coach_headers, queue
):
    job = enqueue(client, trajectories.match_id, coach_headers)
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="player analytics jobs"):
            command.downgrade(migration_config(connection), "0009_trajectory_cleaning")
        assert (
            connection.scalar(
                text("SELECT job_type FROM processing_jobs WHERE id = :id"),
                {"id": job["id"]},
            )
            == "player_analytics"
        )
        command.upgrade(migration_config(connection), "head")
    assert test_jobs.persisted_job(engine, job["id"]).job_type == "player_analytics"


def rewrite_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{key: row[key] for key in columns} for row in rows])


def test_realistic_synthetic_smoke_with_api_reload(
    client,
    coordinates,
    tracks,
    detections,
    source_video,
    settings,
    session,
    engine,
    coach_headers,
    queue,
    record_property,
):
    # Explicit saved artifacts, no detector/tracker/mapper/cleaner is executed.
    points = [
        point(0, 1, 1, track=3),
        point(0.5, 2, 1, track=3),
        point(1, 6, 1, track=3),
        point(1.5, 10, 1, track=3),
        point(2, 11, 1, track=3),
        point(2.25, 13, 1, track=3),
        point(2.5, None, track=3),
        point(3, 14, 1, track=3),
        point(3.5, 15, 1, track=3),
        point(6, 15, 5, track=3, segment=2),
        point(7, 18, 9, track=3, segment=2),
        point(0, 5, 12, track=7),
        point(1, 8, 16, track=7),
        point(2.5, 8, 19, track=7),
    ]
    # Quarter-second samples use an actual tiny 20fps video (160 small frames).
    points = [
        point(
            p.timestamp,
            p.clean[0] if p.clean else None,
            p.clean[1] if p.clean else 0,
            track=p.track_id,
            segment=p.segment_id,
            frame=round(p.timestamp * 20),
        )
        for p in points
    ]
    video = source_video[0]
    video_path = settings.storage_dir / video.relative_storage_path
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (64, 48)
    )
    assert writer.isOpened()
    try:
        for _ in range(160):
            writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    finally:
        writer.release()
    video.file_size_bytes, video.fps, video.frame_count, video.duration_seconds = (
        video_path.stat().st_size,
        20,
        160,
        8,
    )
    source_rows = []
    for p in sorted(points, key=lambda p: (p.frame, p.track_id)):
        x, y = p.clean if p.clean else (-1, 0)
        px, py = (x + 10) * 2, y * 2
        source_rows.append(
            dict(
                frame_number=p.frame,
                timestamp_seconds=p.timestamp,
                track_id=p.track_id,
                x1=px - 1,
                y1=py - 1,
                x2=px + 1,
                y2=py,
                confidence=0.9,
                class_id=0,
                class_name="person",
                frame_width=64,
                frame_height=48,
                pixel_x=px,
                pixel_y=py,
                pitch_x=x,
                pitch_y=y,
                inside_pitch="true" if p.clean else "false",
            )
        )
    rewrite_csv(
        settings.storage_dir / detections.artifact_relative_path,
        DETECTION_COLUMNS,
        source_rows,
    )
    detections.detection_summary = {
        **detections.detection_summary,
        "processed_frames": 160,
        "decoded_frames": 160,
        "total_detections": len(points),
        "average_detections_per_processed_frame": len(points) / 160,
    }
    session.commit()
    match = session.get(Match, coordinates.match_id)
    _, tracks.detection_snapshot = current_detection(
        session, match, video, tracks.calibration_snapshot, settings
    )
    tracks.tracking_summary = {
        **tracks.tracking_summary,
        "processed_frames": 160,
        "total_detections": len(points),
        "total_track_rows": len(points),
    }
    rewrite_csv(
        settings.storage_dir / tracks.artifact_relative_path, TRACK_COLUMNS, source_rows
    )
    session.commit()
    inputs = current_mapping_inputs(session, match, settings)
    coordinates.tracking_snapshot, coordinates.calibration_snapshot = (
        inputs.source.version,
        inputs.calibration,
    )
    coordinate_path = settings.storage_dir / coordinates.artifact_relative_path
    rewrite_csv(coordinate_path, COORDINATE_COLUMNS, source_rows)
    coordinates.coordinate_summary = {
        **coordinates.coordinate_summary,
        "total_rows": len(points),
        "valid_mapped_rows": len(points),
        "inside_pitch_rows": len(points) - 1,
        "outside_pitch_rows": 1,
        "last_frame": 140,
        "artifact_version": file_version(coordinate_path),
    }
    session.commit()
    trajectories = publish_trajectories(session, settings, coordinates, points)
    job = enqueue(client, trajectories.match_id, coach_headers)
    worker.analyze_players(job["id"], 0)
    response = result(client, trajectories.match_id, coach_headers)
    assert response.status_code == 200, response.text
    a, b = response.json()["items"]
    assert a["total_distance_metres"] == 18 and a["active_duration_seconds"] == 3.75
    assert a["average_speed_mps"] == 4.8 and a["max_speed_mps"] == 8
    assert (
        a["sprint_count"] == 1
        and a["sprint_distance_metres"] == 8
        and a["sprint_duration_seconds"] == 1
    )
    assert b["total_distance_metres"] == 8 and b["active_duration_seconds"] == 2.5
    assert (
        b["average_speed_mps"] == 3.2
        and b["max_speed_mps"] == 5
        and b["sprint_count"] == 0
    )
    heatmaps = [
        result(
            client, trajectories.match_id, coach_headers, f"/{row['track_id']}/heatmap"
        ).json()
        for row in (a, b)
    ]
    for row, heatmap in zip((a, b), heatmaps, strict=True):
        assert sum(c["occupancy_seconds"] for c in heatmap["cells"]) == pytest.approx(
            row["active_duration_seconds"]
        )
        assert sum(c["occupancy_fraction"] for c in heatmap["cells"]) == pytest.approx(
            1
        )
    stored = test_jobs.persisted_job(engine, job["id"])
    path = settings.storage_dir / stored.artifact_relative_path
    artifacts = {
        name: [r.model_dump() for r in read_rows(path / f"{name}.csv", name)]
        for name in MODELS
    }
    assert len(artifacts["intervals"]) == 9 and len(artifacts["sprints"]) == 1
    assert sum(r["above_sprint_threshold"] for r in artifacts["intervals"]) == 3
    smoke = {
        "tracks": [a, b],
        "heatmaps": heatmaps,
        "artifacts": artifacts,
        "summary": stored.analytics_summary,
    }
    json.dumps(smoke, allow_nan=False)
    record_property("player_analytics_smoke", smoke)
