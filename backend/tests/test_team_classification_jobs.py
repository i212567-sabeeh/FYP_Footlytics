"""Jersey worker/API tests over saved synthetic tracks; never YOLO or ByteTrack."""

from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import test_detection_jobs
import test_football
import test_jobs
import test_review
import test_tracking_jobs
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import func, inspect, select, update
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.auth.tokens import create_access_token
from app.cv.detector import YoloPlayerDetector
from app.cv.team_pipeline import ClassificationError
from app.cv.tracker import ByteTrackTracker
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.media import MatchVideo, ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.services.domain_common import DomainError
from app.services.frame_service import CalibrationFrame
from app.services.tracking_artifacts import COLUMNS
from app.workers import team_classification as worker
from app.workers.queue import RQJobQueue, get_job_queue

domain = test_football.domain
source_video = test_jobs.source_video
calibrated = test_detection_jobs.calibrated
detections = test_tracking_jobs.detections
tracks = test_review.tracks


@pytest.mark.parametrize(
    "confidence", [float("nan"), float("inf"), -float("inf"), -0.1, 1.1]
)
def test_database_rejects_invalid_confidence(engine, tracks, confidence):
    with create_session_factory(engine)() as session:
        session.add(
            TrackTeamAssignment(
                match_id=tracks.match_id,
                tracking_job_id=tracks.id,
                tracking_version="a" * 64,
                track_id=3,
                automatic_team="unknown",
                automatic_confidence=confidence,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "fault", ["foreign_match", "missing_job", "duplicate", "zero_track", "invalid_team"]
)
def test_assignment_database_constraints(engine, tracks, domain, fault):
    data = dict(
        match_id=tracks.match_id,
        tracking_job_id=tracks.id,
        tracking_version="a" * 64,
        track_id=3,
        automatic_team="unknown",
        automatic_confidence=0.0,
    )
    if fault == "foreign_match":
        data["match_id"] = domain["matches"][1]["id"]
    elif fault == "missing_job":
        data["tracking_job_id"] = 999999
    elif fault == "zero_track":
        data["track_id"] = 0
    elif fault == "invalid_team":
        data["manual_team"] = "red"
    with create_session_factory(engine)() as session:
        session.add(TrackTeamAssignment(**data))
        if fault == "duplicate":
            session.add(TrackTeamAssignment(**data))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("track_id", ["0", "-1", "abc", "1.5", str(2**63)])
def test_invalid_track_identifier_is_rejected(client, tracks, coach_headers, track_id):
    assert (
        patch_team(
            client, tracks.match_id, coach_headers, "team_a", track_id
        ).status_code
        == 422
    )


class RecordingQueue(test_tracking_jobs.RecordingQueue):
    def enqueue_team_classification(self, job_id, attempt, rq_job_id):
        self.enqueue_player_tracking(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, settings, monkeypatch):
    queue = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: queue
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    for cls in (YoloPlayerDetector, ByteTrackTracker):
        monkeypatch.setattr(
            cls, "__init__", Mock(side_effect=AssertionError("Prior CV stage executed"))
        )
    settings.team_sample_interval = 1
    settings.team_min_crop_width = 4
    settings.team_min_crop_height = 4
    yield queue
    client.app.dependency_overrides.pop(get_job_queue, None)


def jersey_image():
    image = np.full((48, 64, 3), (0, 180, 0), np.uint8)
    image[5:40, 10:26] = (0, 0, 255)
    image[5:40, 40:50] = (255, 0, 0)
    return image


@pytest.fixture
def frames(monkeypatch):
    def extract(video, timestamp, settings, *, frame_number):
        success, encoded = cv2.imencode(".jpg", jersey_image())
        assert success
        return CalibrationFrame(
            video.id, frame_number, frame_number / 10, 64, 48, encoded.tobytes()
        )

    mock = Mock(side_effect=extract)
    monkeypatch.setattr(worker, "extract_frame", mock)
    return mock


def enqueue(client, match_id, headers):
    response = client.post(
        f"/api/matches/{match_id}/jobs/team-classification", headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def assignments(client, match_id, headers):
    response = client.get(f"/api/matches/{match_id}/team-assignments", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def patch_team(client, match_id, headers, value, track_id=3):
    return client.patch(
        f"/api/matches/{match_id}/tracks/{track_id}/team",
        headers=headers,
        json={"team": value},
    )


def test_worker_persists_track_assignments_and_real_progress_only_after_success(
    client, tracks, coach_headers, queue, frames, engine, settings, monkeypatch
):
    original = (settings.storage_dir / tracks.artifact_relative_path).read_bytes()
    progress = Mock(wraps=worker._running)
    monkeypatch.setattr(worker, "_running", progress)
    job = enqueue(client, tracks.match_id, coach_headers)
    assert assignments(client, tracks.match_id, coach_headers)["items"] == []
    worker.classify_teams(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed" and stored.progress_percent == 100
    summary = stored.classification_summary
    assert (
        summary["processed_frames"],
        summary["sampled_frames"],
        summary["valid_samples"],
        summary["total_tracks"],
    ) == (4, 3, 6, 2)
    assert summary["team_a_tracks"] == summary["team_b_tracks"] == 1
    assert summary["unknown_tracks"] == 0
    assert [c.kwargs["frame_number"] for c in frames.call_args_list] == [0, 1, 3]
    assert [
        c.kwargs["progress_percent"]
        for c in progress.call_args_list
        if "progress_percent" in c.kwargs
    ] == [25, 50, 75, 99]
    data = assignments(client, tracks.match_id, coach_headers)
    assert data["total"] == 2
    assert {item["effective_team"] for item in data["items"]} == {"team_a", "team_b"}
    assert all(
        item["automatic_confidence"] >= 0.6 and item["manual_team"] is None
        for item in data["items"]
    )
    assert (
        settings.storage_dir / tracks.artifact_relative_path
    ).read_bytes() == original
    public_job = client.get(f"/api/jobs/{job['id']}", headers=coach_headers).json()
    assert public_job["classification_summary"] == summary
    assert not {
        "tracking_snapshot",
        "artifact_relative_path",
        "rq_job_id",
    }.intersection(public_job)
    assert str(settings.storage_dir) not in str(data) + str(public_job)
    worker.classify_teams(job["id"], 0)  # Duplicate delivery must do nothing.
    assert frames.call_count == 3


@pytest.mark.parametrize("manual", ["team_a", "team_b", "unknown"])
def test_manual_override_survives_reclassification_and_can_be_cleared(
    client, tracks, coach_headers, queue, frames, engine, manual, settings
):
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    override = patch_team(client, tracks.match_id, coach_headers, manual)
    assert override.status_code == 200
    before = override.json()
    assert before["effective_team"] == before["manual_team"] == manual
    assert before["updated_by_user_id"] is not None
    settings.team_min_samples = 4  # Rerun now has insufficient evidence.
    rerun = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(rerun["id"], 0)
    current = assignments(client, tracks.match_id, coach_headers)["items"][0]
    assert current["automatic_team"] == "unknown"
    assert current["effective_team"] == manual
    assert current["created_at"] == before["created_at"]
    cleared = patch_team(client, tracks.match_id, coach_headers, None).json()
    assert cleared["manual_team"] is None and cleared["effective_team"] == "unknown"
    with create_session_factory(engine)() as session:
        assert (
            session.scalar(select(func.count()).select_from(TrackTeamAssignment)) == 2
        )


def test_manual_edit_during_sampling_is_preserved(
    client, tracks, coach_headers, queue, frames, monkeypatch
):
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    actual = frames.side_effect

    def edit(*args, **kwargs):
        response = patch_team(client, tracks.match_id, coach_headers, "unknown")
        assert response.status_code == 200
        return actual(*args, **kwargs)

    frames.side_effect = edit
    rerun = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(rerun["id"], 0)
    assert (
        assignments(client, tracks.match_id, coach_headers)["items"][0]["manual_team"]
        == "unknown"
    )


@pytest.mark.parametrize(
    "payload", [{}, {"team": "red"}, {"team": 1}, {"team": "team_a", "extra": True}]
)
def test_invalid_override_rejected(client, tracks, coach_headers, payload):
    response = client.patch(
        f"/api/matches/{tracks.match_id}/tracks/3/team",
        json=payload,
        headers=coach_headers,
    )
    assert response.status_code == 422


def test_missing_assignments_and_unknown_track_are_not_invented(
    client, tracks, coach_headers, queue, frames
):
    assert (
        patch_team(client, tracks.match_id, coach_headers, "team_a").status_code == 404
    )
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    assert (
        patch_team(client, tracks.match_id, coach_headers, "team_a", 999).status_code
        == 404
    )


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
def test_role_permissions_for_read_run_and_override(
    client, tracks, domain, settings, coach_headers, queue, frames, role, read, write
):
    initial = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(initial["id"], 0)
    account = domain["post"](
        "users",
        {
            "email": f"jersey-{role}@example.com",
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
    assert (
        client.get(
            f"/api/matches/{tracks.match_id}/team-assignments", headers=headers
        ).status_code
        == read
    )
    assert patch_team(client, tracks.match_id, headers, "unknown").status_code == (
        200 if write == 202 else 403
    )
    assert (
        client.post(
            f"/api/matches/{tracks.match_id}/jobs/team-classification", headers=headers
        ).status_code
        == write
    )


def test_cross_club_and_anonymous_denied(client, domain, coach_headers, queue):
    foreign = domain["matches"][1]["id"]
    for headers, status in ((coach_headers, 404), ({}, 401)):
        assert (
            client.get(
                f"/api/matches/{foreign}/team-assignments", headers=headers
            ).status_code
            == status
        )
        assert patch_team(client, foreign, headers, "team_a").status_code == status
        assert (
            client.post(
                f"/api/matches/{foreign}/jobs/team-classification", headers=headers
            ).status_code
            == status
        )
    assert not queue.calls


def test_missing_tracking_does_not_rerun_prior_stages(
    client, detections, coach_headers, queue
):
    response = client.post(
        f"/api/matches/{detections.match_id}/jobs/team-classification",
        headers=coach_headers,
    )
    assert response.status_code == 409 and "tracking" in response.text.lower()
    assert not queue.calls


@pytest.mark.parametrize(
    "fault", ["file", "summary", "calibration", "detection", "video"]
)
def test_missing_or_stale_inputs_cannot_be_queued(
    client,
    tracks,
    calibrated,
    source_video,
    session,
    settings,
    coach_headers,
    queue,
    fault,
):
    if fault == "file":
        (settings.storage_dir / tracks.artifact_relative_path).unlink()
    elif fault == "summary":
        tracks.tracking_summary = {**tracks.tracking_summary, "detection_job_id": 999}
    elif fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "detection":
        tracks.detection_snapshot = {}
    else:
        source_video[0].is_active = False
    session.commit()
    response = client.post(
        f"/api/matches/{tracks.match_id}/jobs/team-classification",
        headers=coach_headers,
    )
    assert response.status_code == 409
    assert not queue.calls


@pytest.mark.parametrize(
    "fault",
    ["video", "video_file", "calibration", "tracking", "tracking_file", "detection"],
)
def test_inputs_changed_during_sampling_fail_without_assignments(
    client,
    tracks,
    source_video,
    calibrated,
    detections,
    coach_headers,
    queue,
    frames,
    engine,
    settings,
    fault,
):
    job = enqueue(client, tracks.match_id, coach_headers)
    actual = frames.side_effect
    changed = False

    def mutate(*args, **kwargs):
        nonlocal changed
        if not changed:
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
                elif fault in {"tracking", "detection"}:
                    target = tracks.id if fault == "tracking" else detections.id
                    session.execute(
                        update(ProcessingJob)
                        .where(ProcessingJob.id == target)
                        .values(updated_at=utc_now())
                    )
                else:
                    path = (
                        source_video[1]
                        if fault == "video_file"
                        else settings.storage_dir / tracks.artifact_relative_path
                    )
                    data = path.read_bytes()
                    path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
                session.commit()
        return actual(*args, **kwargs)

    frames.side_effect = mutate
    with pytest.raises((DomainError, ClassificationError)):
        worker.classify_teams(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "failed" and stored.classification_summary is None
    assert str(settings.storage_dir) not in stored.error_message
    with create_session_factory(engine)() as session:
        assert (
            session.scalar(select(func.count()).select_from(TrackTeamAssignment)) == 0
        )


def test_assignment_visibility_is_bound_to_exact_tracking_version(
    client, tracks, coach_headers, queue, frames, session
):
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    assert (
        patch_team(client, tracks.match_id, coach_headers, "unknown").status_code == 200
    )
    tracks.updated_at = utc_now()  # New generation of the same match-local IDs.
    session.commit()
    assert assignments(client, tracks.match_id, coach_headers)["items"] == []
    assert (
        patch_team(client, tracks.match_id, coach_headers, "team_a").status_code == 404
    )
    fresh = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(fresh["id"], 0)
    assert all(
        row["manual_team"] is None
        for row in assignments(client, tracks.match_id, coach_headers)["items"]
    )


def test_new_tracking_job_does_not_inherit_old_manual_teams(
    client, tracks, coach_headers, queue, frames, session, settings
):
    first = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(first["id"], 0)
    assert (
        patch_team(client, tracks.match_id, coach_headers, "unknown").status_code == 200
    )
    new_tracks = ProcessingJob(
        match_id=tracks.match_id,
        video_id=tracks.video_id,
        job_type="player_tracking",
        status="completed",
        current_stage="completed",
        progress_percent=100,
        created_by_user_id=tracks.created_by_user_id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        calibration_snapshot=tracks.calibration_snapshot,
        detection_snapshot=tracks.detection_snapshot,
        tracking_summary=tracks.tracking_summary,
    )
    session.add(new_tracks)
    session.flush()
    relative = tracks.artifact_relative_path.replace(
        f"/jobs/{tracks.id}/", f"/jobs/{new_tracks.id}/"
    )
    path = settings.storage_dir / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(
        (settings.storage_dir / tracks.artifact_relative_path).read_bytes()
    )
    new_tracks.artifact_relative_path = relative
    session.commit()
    assert assignments(client, tracks.match_id, coach_headers)["total"] == 0
    second = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(second["id"], 0)
    current = assignments(client, tracks.match_id, coach_headers)["items"]
    assert all(
        row["tracking_job_id"] == new_tracks.id and row["manual_team"] is None
        for row in current
    )


def test_empty_tracking_publishes_empty_assignments_without_decoding(
    client, tracks, coach_headers, queue, frames, session, settings, engine
):
    path = settings.storage_dir / tracks.artifact_relative_path
    path.write_text(",".join(COLUMNS) + "\n", encoding="utf-8")
    tracks.tracking_summary = {
        **tracks.tracking_summary,
        "unique_tracks": 0,
        "total_track_rows": 0,
    }
    session.commit()
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed_with_warnings"
    assert stored.classification_summary["total_tracks"] == 0
    assert stored.classification_summary["processed_frames"] == 4
    assert assignments(client, tracks.match_id, coach_headers)["total"] == 0
    frames.assert_not_called()


def test_failed_attempt_retry_and_old_delivery_are_safe(
    client, tracks, coach_headers, queue, frames, engine
):
    job = enqueue(client, tracks.match_id, coach_headers)
    actual = frames.side_effect
    frames.side_effect = OSError("/private/storage/sensitive.mp4")
    with pytest.raises(OSError):
        worker.classify_teams(job["id"], 0)
    failed = test_jobs.persisted_job(engine, job["id"])
    assert failed.status == "failed" and "/private" not in failed.error_message
    frames.side_effect = actual
    retry = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert retry.status_code == 202
    worker.classify_teams(job["id"], 0)
    assert test_jobs.persisted_job(engine, job["id"]).status == "queued"
    worker.classify_teams(job["id"], 1)
    assert test_jobs.persisted_job(engine, job["id"]).status == "completed"
    assert len(assignments(client, tracks.match_id, coach_headers)["items"]) == 2
    assert queue.calls[1][1] == 1 and queue.calls[0][2] != queue.calls[1][2]


def test_superseded_attempt_cannot_publish_assignments(
    client, tracks, coach_headers, queue, frames, engine, monkeypatch
):
    job = enqueue(client, tracks.match_id, coach_headers)
    actual = worker._publish

    def supersede(session, job_id, attempt, source, run, settings):
        with create_session_factory(engine)() as other:
            other.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .values(attempt=attempt + 1, status="queued")
            )
            other.commit()
        return actual(session, job_id, attempt, source, run, settings)

    monkeypatch.setattr(worker, "_publish", supersede)
    worker.classify_teams(job["id"], 0)
    assert assignments(client, tracks.match_id, coach_headers)["total"] == 0
    assert test_jobs.persisted_job(engine, job["id"]).status == "queued"


def test_failed_publish_rolls_back_all_assignment_changes(
    client, tracks, coach_headers, queue, frames, engine, monkeypatch
):
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    before = assignments(client, tracks.match_id, coach_headers)
    actual = worker.assignment_query

    def fail_after_terminal_update(*args):
        raise OSError("/private/database/problem")

    monkeypatch.setattr(worker, "assignment_query", fail_after_terminal_update)
    rerun = enqueue(client, tracks.match_id, coach_headers)
    with pytest.raises(OSError):
        worker.classify_teams(rerun["id"], 0)
    assert assignments(client, tracks.match_id, coach_headers) == before
    assert test_jobs.persisted_job(engine, rerun["id"]).status == "failed"
    monkeypatch.setattr(worker, "assignment_query", actual)


def test_queue_failure_and_active_job_conflicts(
    client, tracks, coach_headers, queue, session
):
    queue.unavailable = True
    response = client.post(
        f"/api/matches/{tracks.match_id}/jobs/team-classification",
        headers=coach_headers,
    )
    assert response.status_code == 503
    stored = session.scalar(
        select(ProcessingJob).where(ProcessingJob.job_type == "team_classification")
    )
    assert stored.status == "failed"
    session.commit()
    queue.unavailable = False
    enqueue(client, tracks.match_id, coach_headers)
    for stage in (
        "team-classification",
        "player-tracking",
        "player-detection",
        "video-preparation",
    ):
        assert (
            client.post(
                f"/api/matches/{tracks.match_id}/jobs/{stage}", headers=coach_headers
            ).status_code
            == 409
        )


def test_rq_receives_ids_only_on_existing_queue(settings, monkeypatch):
    queue = RQJobQueue(settings)
    persist = Mock()
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_team_classification(12, 3, "jersey-attempt")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.team_classification.classify_teams",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert job.timeout == settings.detection_job_timeout_seconds
    queue.close()


def test_real_tiny_video_classification_smoke(
    client, tracks, source_video, coach_headers, queue, engine, session
):
    video, path = source_video
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    assert writer.isOpened()
    try:
        for _ in range(4):
            writer.write(jersey_image())
    finally:
        writer.release()
    video.file_size_bytes = path.stat().st_size
    session.commit()
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)  # Real bounded decoder + Lab + clustering.
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed"
    assert stored.classification_summary["valid_samples"] == 6
    assert {
        row["effective_team"]
        for row in assignments(client, tracks.match_id, coach_headers)["items"]
    } == {"team_a", "team_b"}


def test_migration_preserves_existing_tracks_and_blocks_destructive_downgrade(
    engine, tracks, client, coach_headers, queue
):
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0006_player_tracking")
        assert "track_team_assignments" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
    assert (
        test_jobs.persisted_job(engine, tracks.id).artifact_relative_path
        == tracks.artifact_relative_path
    )
    enqueue(client, tracks.match_id, coach_headers)
    with (
        engine.begin() as connection,
        pytest.raises(RuntimeError, match="classification data"),
    ):
        command.downgrade(migration_config(connection), "0006_player_tracking")
