"""Existing RQ boundary with a mocked detector and a four-frame real local clip."""

import csv
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_football
import test_jobs
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import inspect, select, text, update

from alembic import command
from app.auth.tokens import create_access_token
from app.core.jobs import JobStatus
from app.cv.detector import BaseDetector, Detection, DetectionError
from app.cv.homography import compute_homography
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.football import Match
from app.models.media import ProcessingJob
from app.services.domain_common import DomainError
from app.workers import player_detection, video_preparation
from app.workers.queue import QueueUnavailable, RQJobQueue, get_job_queue

domain = test_football.domain
source_video = test_jobs.source_video


class RecordingQueue(test_jobs.RecordingQueue):
    def enqueue_player_detection(self, job_id, attempt, rq_job_id):
        if self.unavailable:
            raise QueueUnavailable("Synthetic Redis failure")
        self.calls.append((job_id, attempt, rq_job_id))


@pytest.fixture
def queue(client):
    instance = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: instance
    yield instance
    client.app.dependency_overrides.pop(get_job_queue, None)


@pytest.fixture
def calibrated(source_video, session, admin):
    video, _path = source_video
    match = session.get(Match, video.match_id)
    images = [(5, 4), (58, 4), (58, 43), (5, 43)]
    pitch = [
        (0, 0),
        (match.pitch_length_metres, 0),
        (match.pitch_length_metres, match.pitch_width_metres),
        (0, match.pitch_width_metres),
    ]
    calibration = PitchCalibration(
        match_id=match.id,
        video_id=video.id,
        source_frame_number=0,
        source_timestamp_seconds=0,
        image_width=64,
        image_height=48,
        pitch_length_metres=match.pitch_length_metres,
        pitch_width_metres=match.pitch_width_metres,
        image_points=[dict(x=x, y=y) for x, y in images],
        pitch_points=[dict(x=x, y=y) for x, y in pitch],
        homography_matrix=compute_homography(images, pitch).tolist(),
        reprojection_error=0,
        created_by_user_id=admin.id,
    )
    session.add(calibration)
    session.commit()
    return calibration


class FixtureDetector(BaseDetector):
    device = "cpu"
    model_name = "synthetic-test-model.pt"

    def detect(self, frame):
        assert frame.shape == (48, 64, 3)
        return [
            Detection((20, 4, 30, 30), 0.9, 0, "person"),
            Detection((0, 0, 2, 47), 0.8, 0, "person"),
        ]


@pytest.fixture
def detector(settings, monkeypatch):
    monkeypatch.setattr(player_detection, "get_settings", lambda: settings)
    factory = Mock(return_value=FixtureDetector())
    monkeypatch.setattr(player_detection, "YoloPlayerDetector", factory)
    return factory


def enqueue(client, source_video, headers):
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/player-detection",
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def job_read(client, job, headers):
    return client.get(f"/api/jobs/{job['id']}", headers=headers).json()


def test_api_only_enqueues_then_worker_streams_roi_csv_real_progress_and_summary(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
    detector,
    settings,
    monkeypatch,
):
    settings.detection_frame_stride = 2
    job = enqueue(client, source_video, coach_headers)
    assert job["job_type"] == "player_detection" and job["detection_summary"] is None
    assert queue.calls[0][:2] == (job["id"], 0)
    detector.assert_not_called()
    progress = []
    original = player_detection._running

    def observe(session, job_id, attempt, **values):
        original(session, job_id, attempt, **values)
        if "progress_percent" in values:
            progress.append(values["progress_percent"])

    monkeypatch.setattr(player_detection, "_running", observe)
    player_detection.detect_players(job["id"], 0)
    result = job_read(client, job, coach_headers)
    assert result["status"] == "completed" and result["progress_percent"] == 100
    assert result["finished_at"] and result["error_message"] is None
    summary = result["detection_summary"]
    assert {
        key: summary[key]
        for key in (
            "decoded_frames",
            "processed_frames",
            "total_detections",
            "average_detections_per_processed_frame",
        )
    } == {
        "decoded_frames": 4,
        "processed_frames": 2,
        "total_detections": 2,
        "average_detections_per_processed_frame": 1,
    }
    assert summary["roi_filter_applied"] and summary["calibration_id"] == calibrated.id
    assert progress == [25, 50, 75, 99, 100]
    assert not {
        "artifact_relative_path",
        "calibration_snapshot",
        "rq_job_id",
    }.intersection(result)
    files = list(settings.storage_dir.glob("tracks/**/*.csv"))
    assert len(files) == 1 and not list(
        settings.storage_dir.glob("tracks/**/*.partial")
    )
    with files[0].open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [int(row["frame_number"]) for row in rows] == [0, 2]
    assert [float(row["timestamp_seconds"]) for row in rows] == pytest.approx([0, 0.2])
    assert all(row["class_name"] == "person" and row["x1"] == "20" for row in rows)
    assert "pitch_x" not in rows[0] and "track_id" not in rows[0]
    player_detection.detect_players(job["id"], 0)
    assert detector.call_count == 1


class CandidateDetector(FixtureDetector):
    def detect(self, frame):
        # A partly occluded player below YOLO_CONFIDENCE, kept only for ByteTrack.
        return [*super().detect(frame), Detection((32, 4, 42, 30), 0.15, 0, "person")]


def test_tracking_candidates_are_stored_but_detection_counts_are_unchanged(
    client, source_video, calibrated, coach_headers, queue, detector, settings
):
    detector.return_value = CandidateDetector()
    job = enqueue(client, source_video, coach_headers)
    player_detection.detect_players(job["id"], 0)
    result = job_read(client, job, coach_headers)
    assert result["status"] == "completed"
    summary = result["detection_summary"]
    assert {
        key: summary[key]
        for key in (
            "total_detections",
            "average_detections_per_processed_frame",
            "low_confidence_detections",
            "confidence_threshold",
            "candidate_confidence_threshold",
        )
    } == {
        "total_detections": 4,
        "average_detections_per_processed_frame": 1,
        "low_confidence_detections": 4,
        "confidence_threshold": 0.25,
        "candidate_confidence_threshold": 0.1,
    }
    (path,) = settings.storage_dir.glob("tracks/**/*.csv")
    with path.open(newline="", encoding="utf-8") as stream:
        confidences = [float(row["confidence"]) for row in csv.DictReader(stream)]
    assert confidences == [0.9, 0.15] * 4


def test_missing_video_and_calibration_are_rejected(
    client, domain, coach_headers, queue
):
    response = client.post(
        f"/api/matches/{domain['matches'][0]['id']}/jobs/player-detection",
        headers=coach_headers,
    )
    assert response.status_code == 409 and not queue.calls


def test_uncalibrated_video_is_rejected(client, source_video, coach_headers, queue):
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/player-detection",
        headers=coach_headers,
    )
    assert response.status_code == 409 and "calibration" in response.json()["detail"]
    assert not queue.calls


@pytest.mark.parametrize("fault", ["pitch_size", "matrix", "archived", "inactive_club"])
def test_invalid_or_stale_calibration_and_inactive_match_are_rejected(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
    session,
    fault,
):
    match = session.get(Match, source_video[0].match_id)
    if fault == "pitch_size":
        match.pitch_length_metres += 1
    elif fault == "matrix":
        calibrated.homography_matrix = [[0] * 3] * 3
    elif fault == "archived":
        match.is_archived = True
    else:
        match.club.is_active = False
    session.commit()
    response = client.post(
        f"/api/matches/{match.id}/jobs/player-detection", headers=coach_headers
    )
    assert response.status_code == (404 if fault == "inactive_club" else 409)
    assert not queue.calls


@pytest.mark.parametrize(
    "role,expected",
    [
        ("coach", 202),
        ("analyst", 202),
        ("admin", 202),
        ("club_management", 403),
        ("player", 403),
    ],
)
def test_detection_execution_permissions(
    client, domain, source_video, calibrated, queue, role, expected, settings
):
    account = domain["post"](
        "users",
        {
            "email": f"detection-{role}@example.com",
            "full_name": f"Detection {role}",
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
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/player-detection",
        headers=headers,
    )
    assert response.status_code == expected
    assert len(queue.calls) == int(expected == 202)


def test_other_club_and_anonymous_cannot_execute(client, domain, coach_headers, queue):
    url = f"/api/matches/{domain['matches'][1]['id']}/jobs/player-detection"
    assert client.post(url, headers=coach_headers).status_code == 404
    assert client.post(url).status_code == 401
    assert not queue.calls


def test_active_detection_blocks_duplicate_preparation_and_replacement(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
):
    job = enqueue(client, source_video, coach_headers)
    for suffix in ("player-detection", "video-preparation"):
        assert (
            client.post(
                f"/api/matches/{job['match_id']}/jobs/{suffix}", headers=coach_headers
            ).status_code
            == 409
        )
    assert (
        client.put(
            f"/api/matches/{job['match_id']}/video",
            headers=coach_headers,
            files={"file": ("replacement.mp4", b"fixture", "video/mp4")},
        ).status_code
        == 409
    )
    assert len(queue.calls) == 1


def test_queue_failure_is_persisted_without_inline_inference(
    client, source_video, calibrated, coach_headers, queue, detector
):
    queue.unavailable = True
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/player-detection",
        headers=coach_headers,
    )
    assert response.status_code == 503
    result = client.get(
        f"/api/matches/{source_video[0].match_id}/jobs", headers=coach_headers
    ).json()["items"][0]
    assert (
        result["status"] == "failed" and result["current_stage"] == "queue_unavailable"
    )
    detector.assert_not_called()


@pytest.mark.parametrize("failure", ["model", "video_open", "inference", "artifact"])
def test_worker_failures_are_safe_and_partial_artifacts_are_removed(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
    detector,
    settings,
    failure,
    monkeypatch,
):
    job = enqueue(client, source_video, coach_headers)
    secret_error = RuntimeError("private/internal/filesystem/model.pt")
    if failure == "model":
        detector.side_effect = secret_error
    elif failure == "video_open":
        source_video[1].write_bytes(b"x" * source_video[1].stat().st_size)
    elif failure == "inference":
        detector.return_value.detect = Mock(side_effect=secret_error)
    else:
        monkeypatch.setattr(
            player_detection.DetectionArtifact,
            "publish",
            Mock(side_effect=secret_error),
        )
    with pytest.raises((RuntimeError, DetectionError)):
        player_detection.detect_players(job["id"], 0)
    result = job_read(client, job, coach_headers)
    assert (
        result["status"] == "failed"
        and result["finished_at"]
        and result["detection_summary"] is None
    )
    assert (
        "private" not in result["error_message"]
        and "Traceback" not in result["error_message"]
    )
    assert not list(settings.storage_dir.glob("tracks/**/*.csv"))
    assert not list(settings.storage_dir.glob("tracks/**/*.partial"))


def test_calibration_change_during_processing_prevents_result_publication(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
    detector,
    settings,
    engine,
):
    job = enqueue(client, source_video, coach_headers)
    original = detector.return_value.detect

    def changed(frame):
        with create_session_factory(engine)() as session:
            session.execute(
                update(PitchCalibration)
                .where(PitchCalibration.id == calibrated.id)
                .values(updated_at=utc_now())
            )
            session.commit()
        return original(frame)

    detector.return_value.detect = changed
    with pytest.raises(DomainError, match="calibration changed"):
        player_detection.detect_players(job["id"], 0)
    assert job_read(client, job, coach_headers)["status"] == "failed"
    assert not list(settings.storage_dir.glob("tracks/**/*.csv"))


def test_retry_uses_current_calibration_and_stale_deliveries_cannot_run(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
    detector,
    engine,
):
    job = enqueue(client, source_video, coach_headers)
    test_jobs.fail_job(engine, job["id"])
    assert (
        client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers).status_code
        == 202
    )
    player_detection.detect_players(job["id"], 0)
    video_preparation.prepare_video(job["id"], 1)
    detector.assert_not_called()
    player_detection.detect_players(job["id"], 1)
    result = job_read(client, job, coach_headers)
    assert result["status"] == "completed" and result["retry_count"] == 1
    assert queue.calls[1][1] == 1 and queue.calls[1][2] != queue.calls[0][2]


def test_incomplete_roi_skips_filter_with_warning_and_zero_detections_stay_zero(
    client,
    source_video,
    calibrated,
    coach_headers,
    queue,
    detector,
    session,
):
    calibrated.pitch_points = [{"x": 1, "y": 1}, *calibrated.pitch_points[1:]]
    session.commit()
    detector.return_value.detect = Mock(return_value=[])
    job = enqueue(client, source_video, coach_headers)
    player_detection.detect_players(job["id"], 0)
    result = job_read(client, job, coach_headers)
    assert result["status"] == "completed_with_warnings"
    assert result["detection_summary"]["processed_frames"] == 4
    assert result["detection_summary"]["total_detections"] == 0
    assert result["detection_summary"]["average_detections_per_processed_frame"] == 0
    assert not result["detection_summary"]["roi_filter_applied"]


def test_rq_delivery_uses_existing_json_queue_and_detection_timeout(
    settings, monkeypatch
):
    queue = RQJobQueue(settings)
    persist = Mock()
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_player_detection(12, 2, "detection-attempt")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.player_detection.detect_players",
        None,
        [],
        {"processing_job_id": 12, "attempt": 2},
    ]
    assert job.timeout == settings.detection_job_timeout_seconds
    assert job.failure_callback is video_preparation.record_rq_failure
    queue.close()


def test_external_failure_callback_covers_detection_attempts(
    client, source_video, calibrated, coach_headers, queue, engine
):
    job = enqueue(client, source_video, coach_headers)
    video_preparation.record_rq_failure(
        SimpleNamespace(kwargs={"processing_job_id": job["id"], "attempt": 0}),
        None,
        RuntimeError,
        RuntimeError(),
        None,
    )
    assert test_jobs.persisted_job(engine, job["id"]).status == JobStatus.FAILED


def test_phase5_upgrade_preserves_preparation_history(
    engine, source_video, client, coach_headers, queue
):
    previous_job = test_jobs.create_job(client, source_video, coach_headers)
    test_jobs.fail_job(engine, previous_job["id"])
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0004_pitch_calibration")
        old = connection.execute(text("SELECT * FROM processing_jobs")).mappings().all()
        command.upgrade(config, "head")
        new = connection.execute(text("SELECT * FROM processing_jobs")).mappings().all()
        assert [{key: row[key] for key in old[0]} for row in new] == old
        assert {
            "calibration_snapshot",
            "detection_summary",
            "artifact_relative_path",
        }.issubset(
            {col["name"] for col in inspect(connection).get_columns("processing_jobs")}
        )
        command.check(config)


def test_downgrade_cannot_silently_remove_detection_history(
    client, source_video, calibrated, coach_headers, queue, engine
):
    job = enqueue(client, source_video, coach_headers)
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="detection jobs exist"):
            command.downgrade(migration_config(connection), "0004_pitch_calibration")
    with create_session_factory(engine)() as session:
        assert (
            session.scalar(
                select(ProcessingJob.id).where(ProcessingJob.id == job["id"])
            )
            == job["id"]
        )
