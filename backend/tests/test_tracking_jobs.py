"""Real ByteTrack worker over fixture CSVs; no YOLO or live Redis required."""

import csv
from unittest.mock import Mock

import numpy as np
import pytest
import test_detection_jobs
import test_football
import test_jobs
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import inspect, select, text, update

from alembic import command
from app.auth.tokens import create_access_token
from app.core.jobs import JobStatus, JobType
from app.cv import tracking_pipeline
from app.cv.detector import Detection, YoloPlayerDetector
from app.cv.tracker import ByteTrackTracker, TrackingError
from app.cv.tracking_rows import tracking_rows
from app.cv.video import VideoFrame, VideoFrames
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.media import MatchVideo, ProcessingJob
from app.schemas.detection import DetectionSummary
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS
from app.services.detection_artifacts import DetectionArtifact
from app.services.detection_inputs import snapshot
from app.services.domain_common import DomainError
from app.services.tracking_artifacts import COLUMNS, TrackingArtifact
from app.workers import player_tracking, video_preparation
from app.workers.queue import RQJobQueue, get_job_queue

domain = test_football.domain
source_video = test_jobs.source_video
calibrated = test_detection_jobs.calibrated


class RecordingQueue(test_detection_jobs.RecordingQueue):
    def enqueue_player_tracking(self, job_id, attempt, rq_job_id):
        self.enqueue_player_detection(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, monkeypatch, settings):
    instance = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: instance
    monkeypatch.setattr(player_tracking, "get_settings", lambda: settings)
    # Tracking must not initialize YOLO or reopen video for frame decoding.
    monkeypatch.setattr(
        YoloPlayerDetector, "__init__", Mock(side_effect=AssertionError("YOLO called"))
    )
    monkeypatch.setattr(
        VideoFrames, "__enter__", Mock(side_effect=AssertionError("Video decoded"))
    )
    yield instance
    client.app.dependency_overrides.pop(get_job_queue, None)


@pytest.fixture
def detections(session, settings, calibrated, source_video, admin):
    video = source_video[0]
    job = ProcessingJob(
        match_id=video.match_id,
        video_id=video.id,
        job_type=JobType.PLAYER_DETECTION,
        status=JobStatus.COMPLETED,
        progress_percent=100,
        current_stage="completed",
        created_by_user_id=admin.id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        calibration_snapshot=snapshot(calibrated),
        detection_summary={
            "processed_frames": 4,
            "decoded_frames": 4,
            "total_detections": 6,
            "average_detections_per_processed_frame": 1.5,
            "frame_stride": 1,
            "frame_width": 64,
            "frame_height": 48,
            "timestamp_fallback_frames": 0,
            "model": "synthetic-fixture.pt",
            "device": "cpu",
            "confidence_threshold": 0.25,
            "inference_image_size": 640,
            "roi_filter_applied": True,
            "roi_skip_reason": None,
            "calibration_id": calibrated.id,
            "calibration_updated_at": calibrated.updated_at.isoformat(),
            "artifact_format": "csv",
            # Current detection output; legacy artifacts omit both keys.
            "candidate_confidence_threshold": 0.1,
            "low_confidence_detections": 0,
        },
    )
    session.add(job)
    session.flush()
    with DetectionArtifact(settings, video.match_id, video.id, job.id, 0) as artifact:
        for number in (0, 1, 3):
            artifact.write_frame(
                VideoFrame(
                    number, number / 10, np.zeros((48, 64, 3), dtype=np.uint8), False
                ),
                [
                    Detection((10 + number, 5, 20 + number, 40), 0.9, 0, "person"),
                    Detection((40, 5, 50, 40), 0.85, 0, "person"),
                ],
            )
        job.artifact_relative_path = artifact.publish()
        session.commit()
        artifact.keep()
    return job


def enqueue(client, match_id, headers):
    response = client.post(
        f"/api/matches/{match_id}/jobs/player-tracking", headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_real_worker_tracks_csv_with_progress_and_private_attempt_artifact(
    client, detections, coach_headers, queue, settings, engine, monkeypatch
):
    original = (settings.storage_dir / detections.artifact_relative_path).read_bytes()
    job = enqueue(client, detections.match_id, coach_headers)
    assert job["status"] == "queued" and job["tracking_summary"] is None
    assert queue.calls[0][:2] == (job["id"], 0)
    progress = []
    actual_transition = player_tracking.transition

    def record(*args, **kwargs):
        if (
            kwargs.get("expected") == (JobStatus.RUNNING,)
            and "progress_percent" in kwargs
        ):
            progress.append(kwargs["progress_percent"])
        return actual_transition(*args, **kwargs)

    monkeypatch.setattr(player_tracking, "transition", record)
    player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.COMPLETED and progress == [25, 50, 75, 99, 100]
    assert stored.tracking_summary["processed_frames"] == 4
    assert stored.tracking_summary["unique_tracks"] == 2
    assert stored.tracking_summary["total_track_rows"] == 6
    # Stride 1 keeps the configured 30-frame buffer: 3 s at the clip's 10 FPS.
    assert stored.tracking_summary["track_buffer_updates"] == 30
    assert stored.tracking_summary["track_buffer_seconds"] == 3.0
    path = settings.storage_dir / stored.artifact_relative_path
    assert f"/jobs/{job['id']}/attempt-0-" in stored.artifact_relative_path
    rows = read_rows(path)
    assert tuple(rows[0]) == COLUMNS
    assert [int(row["frame_number"]) for row in rows] == [0, 0, 1, 1, 3, 3]
    assert [float(row["timestamp_seconds"]) for row in rows] == [
        0,
        0,
        0.1,
        0.1,
        0.3,
        0.3,
    ]
    assert [int(row["track_id"]) for row in rows] == [1, 2, 1, 2, 1, 2]
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert (
        settings.storage_dir / detections.artifact_relative_path
    ).read_bytes() == original
    response = client.get(f"/api/jobs/{job['id']}", headers=coach_headers).json()
    assert not {
        "detection_snapshot",
        "artifact_relative_path",
        "calibration_snapshot",
        "rq_job_id",
    }.intersection(response)
    player_tracking.track_players(job["id"], 0)  # Duplicate delivery does no work.
    assert read_rows(path) == rows


@pytest.mark.parametrize("missing", ["video", "calibration", "detections"])
def test_required_current_inputs(
    client, domain, source_video, calibrated, session, coach_headers, queue, missing
):
    if missing == "video":
        source_video[0].is_active = False
    elif missing == "calibration":
        session.delete(calibrated)
    session.commit()
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/player-tracking",
        headers=coach_headers,
    )
    assert response.status_code == 409 and not queue.calls


@pytest.mark.parametrize(
    "fault", ["calibration", "old_video", "file", "path", "header", "summary", "failed"]
)
def test_missing_invalid_or_stale_detections_rejected(
    client,
    detections,
    source_video,
    calibrated,
    session,
    settings,
    coach_headers,
    queue,
    fault,
):
    path = settings.storage_dir / detections.artifact_relative_path
    if fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "old_video":
        source_video[0].is_active = False
    elif fault == "file":
        path.unlink()
    elif fault == "path":
        detections.artifact_relative_path = "../private.csv"
    elif fault == "header":
        path.write_text("wrong,columns\n", encoding="utf-8")
    elif fault == "summary":
        detections.detection_summary = {
            **detections.detection_summary,
            "processed_frames": 99,
        }
    else:
        detections.status = JobStatus.FAILED
    session.commit()
    response = client.post(
        f"/api/matches/{detections.match_id}/jobs/player-tracking",
        headers=coach_headers,
    )
    assert response.status_code == 409 and not queue.calls
    assert (
        str(settings.storage_dir) not in response.text
        and "private.csv" not in response.text
    )


@pytest.mark.parametrize(
    "role,expected",
    [
        ("admin", 202),
        ("coach", 202),
        ("analyst", 202),
        ("club_management", 403),
        ("player", 403),
    ],
)
def test_tracking_permissions(
    client, domain, detections, settings, queue, role, expected
):
    account = domain["post"](
        "users",
        {
            "email": f"tracking-{role}@example.com",
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
    response = client.post(
        f"/api/matches/{detections.match_id}/jobs/player-tracking", headers=headers
    )
    assert response.status_code == expected
    assert len(queue.calls) == int(expected == 202)


def test_cross_club_and_anonymous_denied(client, domain, coach_headers, queue):
    url = f"/api/matches/{domain['matches'][1]['id']}/jobs/player-tracking"
    assert client.post(url, headers=coach_headers).status_code == 404
    assert client.post(url).status_code == 401
    assert not queue.calls


@pytest.mark.parametrize(
    "fault",
    ["video", "calibration", "detection_version", "same_size_csv", "video_file"],
)
def test_inputs_changed_during_processing_fail_without_publishing(
    client,
    detections,
    source_video,
    calibrated,
    coach_headers,
    queue,
    engine,
    settings,
    monkeypatch,
    fault,
):
    job = enqueue(client, detections.match_id, coach_headers)
    update_tracker = ByteTrackTracker.update
    changed = False

    def mutate(self, boxes):
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
                elif fault == "detection_version":
                    session.execute(
                        update(ProcessingJob)
                        .where(ProcessingJob.id == detections.id)
                        .values(attempt=1, updated_at=utc_now())
                    )
                elif fault == "same_size_csv":
                    path = settings.storage_dir / detections.artifact_relative_path
                    data = path.read_bytes()
                    path.write_bytes(data.replace(b"0.85", b"0.84"))
                else:
                    path = source_video[1]
                    data = path.read_bytes()
                    path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
                session.commit()
        return update_tracker(self, boxes)

    monkeypatch.setattr(ByteTrackTracker, "update", mutate)
    with pytest.raises((DomainError, TrackingError)):
        player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.FAILED and stored.artifact_relative_path is None
    assert str(settings.storage_dir) not in stored.error_message
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 1
    assert not list(settings.storage_dir.rglob("*.partial"))


@pytest.mark.parametrize("when", ["before", "during"])
def test_missing_source_video_has_one_curated_failure(
    client,
    detections,
    source_video,
    coach_headers,
    queue,
    engine,
    settings,
    monkeypatch,
    when,
):
    job = enqueue(client, detections.match_id, coach_headers)
    if when == "before":
        source_video[1].unlink()
    else:
        update_tracker = ByteTrackTracker.update

        def remove(self, boxes):
            source_video[1].unlink(missing_ok=True)
            return update_tracker(self, boxes)

        monkeypatch.setattr(ByteTrackTracker, "update", remove)
    with pytest.raises(TrackingError, match="missing or changed"):
        player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.FAILED and stored.artifact_relative_path is None
    assert stored.error_message == player_tracking.VIDEO_UNAVAILABLE
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 1
    assert not list(settings.storage_dir.rglob("*.partial"))


@pytest.mark.parametrize(
    "fault", ["invalid_box", "nan_time", "out_of_order", "truncated", "wrong_width"]
)
def test_corrupt_csv_fails_safely(
    client, detections, session, settings, coach_headers, queue, engine, fault
):
    path = settings.storage_dir / detections.artifact_relative_path
    rows = read_rows(path)
    if fault == "invalid_box":
        rows[-1]["x2"] = rows[-1]["x1"]
    elif fault == "nan_time":
        rows[-1]["timestamp_seconds"] = "nan"
    elif fault == "out_of_order":
        rows.reverse()
    elif fault == "truncated":
        rows.pop()
    else:
        rows[-1]["frame_width"] = "128"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    job = enqueue(client, detections.match_id, coach_headers)
    with pytest.raises(TrackingError, match="CSV is invalid"):
        player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.FAILED and stored.tracking_summary is None
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 1
    assert not list(settings.storage_dir.rglob("*.partial"))


@pytest.mark.parametrize("at_end", [False, True])
def test_tracking_enforces_the_track_reader_duration_boundary(
    client, detections, source_video, settings, coach_headers, queue, engine, at_end
):
    """Producer and readers share within_video(): frames start before the end."""
    duration = source_video[0].duration_seconds
    last = duration if at_end else duration - 0.001
    path = settings.storage_dir / detections.artifact_relative_path
    rows = read_rows(path)
    for row in rows:
        if row["frame_number"] == "3":
            row["timestamp_seconds"] = str(last)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    job = enqueue(client, detections.match_id, coach_headers)
    if at_end:
        with pytest.raises(TrackingError, match="not within the stored video"):
            player_tracking.track_players(job["id"], 0)
        stored = test_jobs.persisted_job(engine, job["id"])
        assert stored.status == JobStatus.FAILED
        assert stored.artifact_relative_path is None
        assert stored.error_message == tracking_pipeline.OUTSIDE_VIDEO
        assert not list(settings.storage_dir.rglob("*.partial"))
        return
    player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.COMPLETED
    summary = DetectionSummary.model_validate(detections.detection_summary)
    output = settings.storage_dir / stored.artifact_relative_path
    # The real downstream reader accepts everything tracking published.
    assert list(tracking_rows(output, summary, duration))[-1].timestamp == last


def test_failed_retry_and_old_delivery_cannot_overwrite_new_artifact(
    client, detections, coach_headers, queue, engine, settings, monkeypatch
):
    job = enqueue(client, detections.match_id, coach_headers)
    actual_publish = TrackingArtifact.publish
    with monkeypatch.context() as patch:

        def fail_after_publish(artifact):
            actual_publish(artifact)
            raise OSError("/private/storage/path")

        patch.setattr(TrackingArtifact, "publish", fail_after_publish)
        with pytest.raises(OSError):
            player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.FAILED and "/private" not in stored.error_message
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 1
    retried = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert retried.status_code == 202
    player_tracking.track_players(job["id"], 0)
    assert test_jobs.persisted_job(engine, job["id"]).status == JobStatus.QUEUED
    player_tracking.track_players(job["id"], 1)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert (
        stored.status == JobStatus.COMPLETED
        and "/attempt-1-" in stored.artifact_relative_path
    )
    assert queue.calls[1][1] == 1 and queue.calls[0][2] != queue.calls[1][2]
    player_tracking.track_players(job["id"], 0)
    assert (
        test_jobs.persisted_job(engine, job["id"]).artifact_relative_path
        == stored.artifact_relative_path
    )


def test_empty_detections_and_stride_have_real_frame_progress(
    client, detections, settings, session, coach_headers, queue, engine
):
    path = settings.storage_dir / detections.artifact_relative_path
    path.write_text(path.read_text().splitlines()[0] + "\n", encoding="utf-8")
    detections.detection_summary = {
        **detections.detection_summary,
        "total_detections": 0,
        "average_detections_per_processed_frame": 0,
        "frame_stride": 2,
        "processed_frames": 2,
    }
    session.commit()
    job = enqueue(client, detections.match_id, coach_headers)
    player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.COMPLETED_WITH_WARNINGS
    assert stored.tracking_summary["processed_frames"] == 2
    assert stored.tracking_summary["unique_tracks"] == 0
    # Stride 2 halves the updates, so lost tracks keep the same 3 s memory.
    assert stored.tracking_summary["track_buffer_updates"] == 15
    assert stored.tracking_summary["track_buffer_seconds"] == 3.0
    assert read_rows(settings.storage_dir / stored.artifact_relative_path) == []


def test_low_confidence_candidate_keeps_player_id_through_occlusion(
    client, detections, session, settings, coach_headers, queue, engine
):
    """ByteTrack's second association extends a track with a stored candidate."""
    rows = []
    for number in range(4):
        # Player A is partly occluded on frame 3, so YOLO is only 15% confident.
        score = 0.15 if number == 3 else 0.9
        rows += [
            (number, number / 10, 10 + number, 5, 20 + number, 40, score)
            + (0, "person", 64, 48),
            (number, number / 10, 40, 5, 50, 40, 0.85, 0, "person", 64, 48),
        ]
    path = settings.storage_dir / detections.artifact_relative_path
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(DETECTION_COLUMNS)
        writer.writerows(rows)
    detections.detection_summary = {
        **detections.detection_summary,
        "total_detections": 7,
        "low_confidence_detections": 1,
        "average_detections_per_processed_frame": 7 / 4,
    }
    session.commit()
    job = enqueue(client, detections.match_id, coach_headers)
    player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.COMPLETED and stored.warning_message is None
    tracked = read_rows(settings.storage_dir / stored.artifact_relative_path)
    player_a = {
        r["frame_number"]: r["track_id"] for r in tracked if float(r["x1"]) < 30
    }
    assert list(player_a) == ["0", "1", "2", "3"] and len(set(player_a.values())) == 1
    assert {
        key: stored.tracking_summary[key]
        for key in (
            "total_detections",
            "low_confidence_detections",
            "total_track_rows",
            "unique_tracks",
            "low_confidence_association",
        )
    } == {
        "total_detections": 7,
        "low_confidence_detections": 1,
        "total_track_rows": 8,
        "unique_tracks": 2,
        "low_confidence_association": True,
    }
    # Shared result guards accept more track rows than reported detections.
    review = client.get(
        f"/api/matches/{detections.match_id}/tracking/summary", headers=coach_headers
    )
    assert review.status_code == 200 and review.json()["tracked_rows"] == 8


def test_legacy_detections_still_track_but_warn_without_candidates(
    client, detections, session, coach_headers, queue, engine
):
    legacy = dict(detections.detection_summary)
    del legacy["candidate_confidence_threshold"], legacy["low_confidence_detections"]
    detections.detection_summary = legacy
    session.commit()
    job = enqueue(client, detections.match_id, coach_headers)
    player_tracking.track_players(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.COMPLETED_WITH_WARNINGS
    assert stored.warning_message == player_tracking.LOW_CONFIDENCE_UNAVAILABLE
    assert stored.tracking_summary["low_confidence_association"] is False
    assert stored.tracking_summary["total_track_rows"] == 6


def test_queue_failure_persists_safe_error_without_processing(
    client, detections, coach_headers, queue, session
):
    queue.unavailable = True
    response = client.post(
        f"/api/matches/{detections.match_id}/jobs/player-tracking",
        headers=coach_headers,
    )
    assert response.status_code == 503
    job = session.scalar(
        select(ProcessingJob).where(ProcessingJob.job_type == JobType.PLAYER_TRACKING)
    )
    assert job.status == JobStatus.FAILED and job.artifact_relative_path is None


def test_active_tracking_blocks_other_jobs(client, detections, coach_headers, queue):
    enqueue(client, detections.match_id, coach_headers)
    for kind in ("player-tracking", "player-detection", "video-preparation"):
        assert (
            client.post(
                f"/api/matches/{detections.match_id}/jobs/{kind}", headers=coach_headers
            ).status_code
            == 409
        )


def test_rq_delivers_only_ids_on_existing_queue(settings, monkeypatch):
    queue = RQJobQueue(settings)
    persist = Mock()
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_player_tracking(12, 3, "tracking-attempt")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.player_tracking.track_players",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert job.timeout == settings.detection_job_timeout_seconds
    assert job.failure_callback is video_preparation.record_rq_failure
    queue.close()


def test_retry_requires_current_detections(
    client, detections, calibrated, coach_headers, queue, engine, session
):
    job = enqueue(client, detections.match_id, coach_headers)
    test_jobs.fail_job(engine, job["id"])
    calibrated.updated_at = utc_now()
    session.commit()
    response = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert response.status_code == 409 and "stale" in response.json()["detail"]
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == JobStatus.FAILED and stored.attempt == 0
    assert len(queue.calls) == 1


def test_worker_ignores_wrong_job_type_and_old_attempt(
    detections, queue, engine, monkeypatch
):
    construct = Mock(side_effect=AssertionError("Must not construct tracker"))
    monkeypatch.setattr(player_tracking, "ByteTrackTracker", construct)
    with create_session_factory(engine)() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == detections.id)
            .values(status=JobStatus.QUEUED)
        )
        session.commit()
    player_tracking.track_players(detections.id, 0)
    player_tracking.track_players(detections.id, 99)
    assert test_jobs.persisted_job(engine, detections.id).status == JobStatus.QUEUED
    construct.assert_not_called()


def test_replaced_video_detections_do_not_count_as_current(
    client, detections, source_video, calibrated, session, coach_headers, queue
):
    old_video = source_video[0]
    old_video.is_active = False
    session.flush()
    replacement = MatchVideo(
        match_id=old_video.match_id,
        original_filename="replacement.mp4",
        stored_filename="replacement.mp4",
        relative_storage_path=f"raw/matches/{old_video.match_id}/replacement.mp4",
        file_size_bytes=old_video.file_size_bytes,
        mime_type="video/mp4",
        width=64,
        height=48,
        fps=10,
        duration_seconds=0.4,
        frame_count=4,
        uploaded_by_user_id=old_video.uploaded_by_user_id,
    )
    session.add(replacement)
    session.flush()
    # Valid current calibration exists, but only the retired video has detections.
    session.add(
        PitchCalibration(
            **{
                column.name: getattr(calibrated, column.name)
                for column in PitchCalibration.__table__.columns
                if column.name not in {"id", "video_id", "created_at", "updated_at"}
            },
            video_id=replacement.id,
        )
    )
    session.commit()
    response = client.post(
        f"/api/matches/{detections.match_id}/jobs/player-tracking",
        headers=coach_headers,
    )
    assert (
        response.status_code == 409
        and "detections are missing" in response.json()["detail"]
    )
    assert not queue.calls


def test_tracking_migration_preserves_detection_history(engine, detections):
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0005_player_detection")
        old = connection.execute(text("SELECT * FROM processing_jobs")).mappings().all()
        command.upgrade(config, "head")
        new = connection.execute(text("SELECT * FROM processing_jobs")).mappings().all()
        assert [{key: row[key] for key in old[0]} for row in new] == old
        assert {"tracking_summary", "detection_snapshot"}.issubset(
            {
                column["name"]
                for column in inspect(connection).get_columns("processing_jobs")
            }
        )
        command.check(config)


def test_downgrade_refuses_to_delete_tracking_history(
    client, detections, coach_headers, queue, engine
):
    job = enqueue(client, detections.match_id, coach_headers)
    with engine.begin() as connection:
        config = migration_config(connection)
        # Exercise revision 0006's guard at its own schema version. Newer,
        # successfully downgraded revisions need not retain current ORM columns.
        command.downgrade(config, "0006_player_tracking")
        with pytest.raises(RuntimeError, match="tracking jobs exist"):
            command.downgrade(config, "0005_player_detection")
        assert (
            connection.scalar(
                select(ProcessingJob.job_type).where(ProcessingJob.id == job["id"])
            )
            == JobType.PLAYER_TRACKING
        )
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0006_player_tracking"
        )
        command.upgrade(config, "head")
        command.check(config)
    assert (
        test_jobs.persisted_job(engine, job["id"]).job_type == JobType.PLAYER_TRACKING
    )
