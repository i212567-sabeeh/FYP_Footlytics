"""Saved-track coordinate jobs/API with exact synthetic geometry and no CV reruns."""

import csv
from unittest.mock import Mock

import cv2
import pytest
import test_football
import test_jobs
import test_review
import test_tracking_jobs
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.auth.tokens import create_access_token
from app.cv import coordinate_pipeline, homography, team_classifier
from app.cv.coordinate_pipeline import CoordinateMappingError
from app.cv.detector import YoloPlayerDetector
from app.cv.tracker import ByteTrackTracker
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.services.coordinate_artifacts import COLUMNS, CoordinateArtifact
from app.services.domain_common import DomainError
from app.services.tracking_artifacts import COLUMNS as TRACK_COLUMNS
from app.workers import coordinate_mapping as worker
from app.workers.queue import RQJobQueue, get_job_queue

domain = test_football.domain
source_video = test_jobs.source_video
detections = test_tracking_jobs.detections
tracks = test_review.tracks


@pytest.fixture
def calibrated(source_video, session, admin):
    video = source_video[0]
    match = session.get(Match, video.match_id)
    match.pitch_length_metres, match.pitch_width_metres = 30, 20
    images = [(20, 0), (60, 0), (60, 40), (20, 40)]
    pitch = [(0, 0), (20, 0), (20, 20), (0, 20)]
    calibration = PitchCalibration(
        match_id=match.id,
        video_id=video.id,
        source_frame_number=0,
        source_timestamp_seconds=0,
        image_width=64,
        image_height=48,
        pitch_length_metres=30,
        pitch_width_metres=20,
        image_points=[{"x": x, "y": y} for x, y in images],
        pitch_points=[{"x": x, "y": y} for x, y in pitch],
        homography_matrix=[[0.5, 0, -10], [0, 0.5, 0], [0, 0, 1]],
        reprojection_error=0,
        created_by_user_id=admin.id,
    )
    session.add(calibration)
    session.commit()
    return calibration


class RecordingQueue(test_tracking_jobs.RecordingQueue):
    def enqueue_coordinate_mapping(self, job_id, attempt, rq_job_id):
        self.enqueue_player_tracking(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, settings, monkeypatch):
    queue = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: queue
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    for cls in (YoloPlayerDetector, ByteTrackTracker):
        monkeypatch.setattr(
            cls, "__init__", Mock(side_effect=AssertionError("Upstream CV executed"))
        )
    monkeypatch.setattr(
        team_classifier,
        "classify_tracks",
        Mock(side_effect=AssertionError("Team classification executed")),
    )
    monkeypatch.setattr(
        homography,
        "compute_homography",
        Mock(side_effect=AssertionError("Calibration refitted")),
    )
    monkeypatch.setattr(
        cv2, "VideoCapture", Mock(side_effect=AssertionError("Video decoded"))
    )
    yield queue
    client.app.dependency_overrides.pop(get_job_queue, None)


def enqueue(client, match_id, headers):
    response = client.post(
        f"/api/matches/{match_id}/jobs/coordinate-mapping", headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def summary(client, match_id, headers):
    return client.get(f"/api/matches/{match_id}/coordinates/summary", headers=headers)


def rows_at(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def rewrite(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRACK_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_coordinate_mapping_smoke_real_homography_and_persisted_csv(
    client, tracks, coach_headers, queue, settings, engine, monkeypatch
):
    original = (settings.storage_dir / tracks.artifact_relative_path).read_bytes()
    monkeypatch.setattr(coordinate_pipeline, "MAPPING_BATCH_ROWS", 2)
    progress = Mock(wraps=worker._running)
    transform = Mock(wraps=homography.transform_points)
    monkeypatch.setattr(worker, "_running", progress)
    monkeypatch.setattr(homography, "transform_points", transform)
    job = enqueue(client, tracks.match_id, coach_headers)
    assert job["job_type"] == "coordinate_mapping" and job["coordinate_summary"] is None
    assert queue.calls[0][:2] == (job["id"], 0)
    assert summary(client, tracks.match_id, coach_headers).status_code == 409
    worker.map_coordinates(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed" and stored.progress_percent == 100
    output_path = settings.storage_dir / stored.artifact_relative_path
    assert f"/jobs/{job['id']}/attempt-0-" in stored.artifact_relative_path
    output = rows_at(output_path)
    assert tuple(output[0]) == COLUMNS
    assert [int(row["frame_number"]) for row in output] == [0, 0, 1, 1, 3, 3]
    assert [int(row["track_id"]) for row in output] == [3, 7, 3, 7, 3, 7]
    assert [float(row["pixel_x"]) for row in output] == [15, 45, 16, 45, 18, 45]
    assert [float(row["pixel_y"]) for row in output] == [40] * 6
    assert [float(row["pitch_x"]) for row in output] == [-2.5, 12.5, -2, 12.5, -1, 12.5]
    assert [float(row["pitch_y"]) for row in output] == [20] * 6
    assert [row["inside_pitch"] for row in output] == ["false", "true"] * 3
    assert all(float(row["confidence"]) in (0.85, 0.9) for row in output)
    assert (
        settings.storage_dir / tracks.artifact_relative_path
    ).read_bytes() == original
    assert not list(settings.storage_dir.rglob("*.partial"))
    result = summary(client, tracks.match_id, coach_headers)
    assert result.status_code == 200, result.text
    data = result.json()
    assert (data["total_rows"], data["valid_mapped_rows"], data["unique_tracks"]) == (
        6,
        6,
        2,
    )
    assert data["inside_pitch_rows"] == data["outside_pitch_rows"] == 3
    assert (data["pitch_length_metres"], data["pitch_width_metres"]) == (30, 20)
    assert (
        data["coordinate_unit"] == "metres"
        and data["x_axis"] == "length"
        and data["y_axis"] == "width"
    )
    assert (data["first_frame"], data["last_frame"]) == (0, 3)
    assert transform.call_count >= 3
    assert [
        c.kwargs["progress_percent"]
        for c in progress.call_args_list
        if "progress_percent" in c.kwargs
    ] == [33, 66, 99, 100]
    stages = [
        c.kwargs["current_stage"]
        for c in progress.call_args_list
        if "current_stage" in c.kwargs
    ]
    assert stages == ["mapping_coordinates", "saving_coordinates", "completed"]
    public_job = client.get(f"/api/jobs/{job['id']}", headers=coach_headers).json()
    assert not {
        "artifact_relative_path",
        "tracking_snapshot",
        "calibration_snapshot",
    }.intersection(public_job)
    assert "artifact_version" not in public_job["coordinate_summary"]
    assert str(settings.storage_dir) not in result.text
    with create_session_factory(engine)() as session:
        assert (
            session.scalar(select(func.count()).select_from(TrackTeamAssignment)) == 0
        )
    worker.map_coordinates(job["id"], 0)  # Duplicate delivery is ignored.
    assert (
        output_path.read_bytes() and len(list(settings.storage_dir.rglob("*.csv"))) == 3
    )


@pytest.mark.parametrize(
    "fault", ["zero_width", "nan", "inf", "reversed", "nonnumeric"]
)
def test_invalid_boxes_skip_rows_without_repair_or_corrupt_output(
    client, tracks, coach_headers, queue, settings, engine, fault
):
    path = settings.storage_dir / tracks.artifact_relative_path
    rows = rows_at(path)
    row = rows[0]
    row["x2"] = {
        "zero_width": row["x1"],
        "nan": "nan",
        "inf": "inf",
        "reversed": "0",
        "nonnumeric": "bad",
    }[fault]
    rewrite(path, rows)
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.map_coordinates(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed_with_warnings"
    assert stored.coordinate_summary["skipped_invalid_boxes"] == 1
    assert stored.coordinate_summary["valid_mapped_rows"] == 5
    assert len(rows_at(settings.storage_dir / stored.artifact_relative_path)) == 5


@pytest.mark.parametrize(
    "fault", ["timestamp", "order", "truncated", "duplicate", "extra_column"]
)
def test_malformed_tracking_metadata_fails_without_final_artifact(
    client, tracks, coach_headers, queue, settings, engine, fault
):
    path = settings.storage_dir / tracks.artifact_relative_path
    rows = rows_at(path)
    if fault == "timestamp":
        rows[-1]["timestamp_seconds"] = "nan"
    elif fault == "order":
        rows.reverse()
    elif fault == "truncated":
        rows.pop()
    elif fault == "duplicate":
        rows[1] = rows[0]
    rewrite(path, rows)
    if fault == "extra_column":
        path.write_text(
            path.read_text().replace("0,0.0,3", "0,0.0,3,unexpected"), encoding="utf-8"
        )
    job = enqueue(client, tracks.match_id, coach_headers)
    with pytest.raises(CoordinateMappingError):
        worker.map_coordinates(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "failed" and stored.artifact_relative_path is None
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 2


def test_empty_tracking_completes_with_header_and_empty_summary(
    client, tracks, session, settings, coach_headers, queue, engine
):
    (settings.storage_dir / tracks.artifact_relative_path).write_text(
        ",".join(TRACK_COLUMNS) + "\n", encoding="utf-8"
    )
    tracks.tracking_summary = {
        **tracks.tracking_summary,
        "total_track_rows": 0,
        "unique_tracks": 0,
    }
    session.commit()
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.map_coordinates(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed_with_warnings"
    assert rows_at(settings.storage_dir / stored.artifact_relative_path) == []
    data = summary(client, tracks.match_id, coach_headers).json()
    assert data["total_rows"] == data["valid_mapped_rows"] == data["unique_tracks"] == 0
    assert data["first_frame"] is data["last_frame"] is None


def test_missing_tracking_is_clear_and_never_enqueues_prior_stages(
    client, detections, coach_headers, queue
):
    response = client.post(
        f"/api/matches/{detections.match_id}/jobs/coordinate-mapping",
        headers=coach_headers,
    )
    assert response.status_code == 409 and "tracking" in response.text.lower()
    assert not queue.calls


@pytest.mark.parametrize(
    "fault",
    [
        "video",
        "calibration",
        "invalid_homography",
        "dimensions",
        "tracking_file",
        "tracking_stale",
    ],
)
def test_missing_or_stale_inputs_are_rejected_before_queueing(
    client,
    tracks,
    source_video,
    calibrated,
    session,
    settings,
    coach_headers,
    queue,
    fault,
):
    if fault == "video":
        source_video[0].is_active = False
    elif fault == "calibration":
        session.delete(calibrated)
    elif fault == "invalid_homography":
        calibrated.homography_matrix = [[0, 0, 0]] * 3
    elif fault == "dimensions":
        session.get(Match, tracks.match_id).pitch_width_metres = 19
    elif fault == "tracking_file":
        (settings.storage_dir / tracks.artifact_relative_path).unlink()
    else:
        tracks.detection_snapshot = {}
    session.commit()
    response = client.post(
        f"/api/matches/{tracks.match_id}/jobs/coordinate-mapping", headers=coach_headers
    )
    assert response.status_code == 409
    assert not queue.calls


@pytest.mark.parametrize(
    "fault",
    [
        "video",
        "calibration",
        "matrix_only",
        "tracking",
        "new_tracking_job",
        "tracking_file",
        "video_file",
    ],
)
def test_input_changes_during_mapping_cannot_publish(
    client,
    tracks,
    source_video,
    calibrated,
    coach_headers,
    queue,
    settings,
    engine,
    monkeypatch,
    fault,
):
    job = enqueue(client, tracks.match_id, coach_headers)
    actual_write = CoordinateArtifact.write_position
    changed = False

    def mutate(artifact, row, position):
        nonlocal changed
        actual_write(artifact, row, position)
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
            elif fault == "matrix_only":
                session.execute(
                    update(PitchCalibration)
                    .where(PitchCalibration.id == calibrated.id)
                    .values(
                        homography_matrix=[[0.5, 0, -9], [0, 0.5, 0], [0, 0, 1]],
                        updated_at=calibrated.updated_at,
                    )
                )
            elif fault == "tracking":
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == tracks.id)
                    .values(updated_at=utc_now())
                )
            elif fault == "new_tracking_job":
                newer = ProcessingJob(
                    match_id=tracks.match_id,
                    video_id=tracks.video_id,
                    job_type="player_tracking",
                    status="completed",
                    progress_percent=100,
                    current_stage="completed",
                    created_by_user_id=tracks.created_by_user_id,
                    attempt=0,
                    retry_count=0,
                    finished_at=utc_now(),
                    calibration_snapshot=tracks.calibration_snapshot,
                    detection_snapshot=tracks.detection_snapshot,
                    tracking_summary=tracks.tracking_summary,
                )
                session.add(newer)
                session.flush()
                relative = tracks.artifact_relative_path.replace(
                    f"/jobs/{tracks.id}/", f"/jobs/{newer.id}/"
                )
                target = settings.storage_dir / relative
                target.parent.mkdir(parents=True)
                target.write_bytes(
                    (settings.storage_dir / tracks.artifact_relative_path).read_bytes()
                )
                newer.artifact_relative_path = relative
            else:
                path = (
                    source_video[1]
                    if fault == "video_file"
                    else settings.storage_dir / tracks.artifact_relative_path
                )
                data = path.read_bytes()
                path.write_bytes(
                    data.replace(b"0.85", b"0.84")
                    if fault == "tracking_file"
                    else data[:-1] + bytes([data[-1] ^ 1])
                )
            session.commit()

    publish = Mock(wraps=CoordinateArtifact.publish)
    monkeypatch.setattr(CoordinateArtifact, "write_position", mutate)
    monkeypatch.setattr(CoordinateArtifact, "publish", publish)
    with pytest.raises((DomainError, CoordinateMappingError)):
        worker.map_coordinates(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "failed" and stored.artifact_relative_path is None
    assert (
        stored.coordinate_summary is None
        and str(settings.storage_dir) not in stored.error_message
    )
    publish.assert_not_called()
    assert not list(settings.storage_dir.rglob("*.partial"))


@pytest.mark.parametrize("fault", ["nan", "shape", "horizon"])
def test_numerical_mapping_errors_fail_safely(
    client, tracks, coach_headers, queue, settings, engine, monkeypatch, fault
):
    actual = homography.transform_points

    def invalid(points, matrix):
        if not points:
            return actual(points, matrix)
        if fault == "horizon":
            raise ValueError("A point lies on the homography horizon")
        return [(float("nan"), 0)] * len(points) if fault == "nan" else [(1, 2, 3)]

    monkeypatch.setattr(homography, "transform_points", invalid)
    job = enqueue(client, tracks.match_id, coach_headers)
    with pytest.raises(CoordinateMappingError, match="mapped safely"):
        worker.map_coordinates(job["id"], 0)
    assert test_jobs.persisted_job(engine, job["id"]).status == "failed"
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 2
    assert not list(settings.storage_dir.rglob("*.partial"))


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
    client, tracks, coach_headers, queue, domain, settings, role, read, write
):
    initial = enqueue(client, tracks.match_id, coach_headers)
    worker.map_coordinates(initial["id"], 0)
    account = domain["post"](
        "users",
        {
            "email": f"coordinates-{role}@example.com",
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
    assert summary(client, tracks.match_id, headers).status_code == read
    assert (
        client.post(
            f"/api/matches/{tracks.match_id}/jobs/coordinate-mapping", headers=headers
        ).status_code
        == write
    )


def test_cross_club_and_anonymous_denied(client, domain, coach_headers, queue):
    foreign = domain["matches"][1]["id"]
    for headers, status in ((coach_headers, 404), ({}, 401)):
        assert summary(client, foreign, headers).status_code == status
        assert (
            client.post(
                f"/api/matches/{foreign}/jobs/coordinate-mapping", headers=headers
            ).status_code
            == status
        )
    assert not queue.calls


@pytest.mark.parametrize(
    "match_id,status",
    [(0, 422), (-1, 422), ("invalid", 422), ("1.5", 422), (2**63, 422), (999999, 404)],
)
def test_invalid_or_missing_match_ids_never_enqueue(
    client, coach_headers, queue, match_id, status
):
    assert summary(client, match_id, coach_headers).status_code == status
    assert (
        client.post(
            f"/api/matches/{match_id}/jobs/coordinate-mapping", headers=coach_headers
        ).status_code
        == status
    )
    assert not queue.calls


def test_failed_retry_preserves_previous_valid_output(
    client, tracks, coach_headers, queue, engine, settings, monkeypatch
):
    first = enqueue(client, tracks.match_id, coach_headers)
    worker.map_coordinates(first["id"], 0)
    old = test_jobs.persisted_job(engine, first["id"])
    path = settings.storage_dir / old.artifact_relative_path
    old_bytes = path.read_bytes()
    second = enqueue(client, tracks.match_id, coach_headers)
    real_publish = CoordinateArtifact.publish
    with monkeypatch.context() as patch:

        def fail_after_publish(artifact):
            real_publish(artifact)
            raise OSError("/private/coordinate/storage")

        patch.setattr(CoordinateArtifact, "publish", fail_after_publish)
        with pytest.raises(OSError):
            worker.map_coordinates(second["id"], 0)
    failed = test_jobs.persisted_job(engine, second["id"])
    assert failed.status == "failed" and "/private" not in failed.error_message
    assert failed.artifact_relative_path is None
    assert path.read_bytes() == old_bytes
    assert (
        summary(client, tracks.match_id, coach_headers).json()["job_id"] == first["id"]
    )
    retry = client.post(f"/api/jobs/{second['id']}/retry", headers=coach_headers)
    assert retry.status_code == 202
    worker.map_coordinates(second["id"], 0)
    assert test_jobs.persisted_job(engine, second["id"]).status == "queued"
    worker.map_coordinates(second["id"], 1)
    latest = test_jobs.persisted_job(engine, second["id"])
    assert (
        latest.status == "completed" and "/attempt-1-" in latest.artifact_relative_path
    )
    assert latest.artifact_relative_path != old.artifact_relative_path
    assert (
        summary(client, tracks.match_id, coach_headers).json()["job_id"] == second["id"]
    )
    assert path.read_bytes() == old_bytes and not list(
        settings.storage_dir.rglob("*.partial")
    )


def test_stale_queue_attempt_cannot_publish(
    client, tracks, coach_headers, queue, engine, settings, monkeypatch
):
    job = enqueue(client, tracks.match_id, coach_headers)
    actual = worker.map_tracking

    def supersede(*args, **kwargs):
        result = actual(*args, **kwargs)
        with create_session_factory(engine)() as session:
            session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job["id"])
                .values(attempt=1, status="queued")
            )
            session.commit()
        return result

    monkeypatch.setattr(worker, "map_tracking", supersede)
    worker.map_coordinates(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "queued" and stored.artifact_relative_path is None
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 2


@pytest.mark.parametrize(
    "fault", ["calibration", "tracking", "source", "output", "summary"]
)
def test_stale_or_damaged_coordinates_are_not_returned_as_current(
    client,
    tracks,
    calibrated,
    source_video,
    coach_headers,
    queue,
    settings,
    session,
    engine,
    fault,
):
    job = enqueue(client, tracks.match_id, coach_headers)
    worker.map_coordinates(job["id"], 0)
    if fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "tracking":
        tracks.updated_at = utc_now()
    elif fault == "source":
        source_video[0].is_active = False
    else:
        stored = session.get(ProcessingJob, job["id"])
        if fault == "output":
            path = settings.storage_dir / stored.artifact_relative_path
            path.write_text(path.read_text().replace("12.5", "12.4"), encoding="utf-8")
        else:
            stored.coordinate_summary = {
                **stored.coordinate_summary,
                "valid_mapped_rows": 999,
            }
    session.commit()
    assert summary(client, tracks.match_id, coach_headers).status_code == 409


def test_team_corrections_do_not_invalidate_mapping(
    client, tracks, coach_headers, queue, engine, settings, monkeypatch
):
    job = enqueue(client, tracks.match_id, coach_headers)
    actual = CoordinateArtifact.write_position
    changed = False

    def correct_team(artifact, row, point):
        nonlocal changed
        actual(artifact, row, point)
        if changed:
            return
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

    monkeypatch.setattr(CoordinateArtifact, "write_position", correct_team)
    worker.map_coordinates(job["id"], 0)
    assert summary(client, tracks.match_id, coach_headers).status_code == 200


def test_queue_failure_and_active_job_conflicts(
    client, tracks, coach_headers, queue, session
):
    queue.unavailable = True
    response = client.post(
        f"/api/matches/{tracks.match_id}/jobs/coordinate-mapping", headers=coach_headers
    )
    assert response.status_code == 503
    assert (
        session.scalar(
            select(ProcessingJob).where(ProcessingJob.job_type == "coordinate_mapping")
        ).status
        == "failed"
    )
    session.commit()
    queue.unavailable = False
    enqueue(client, tracks.match_id, coach_headers)
    for stage in (
        "coordinate-mapping",
        "player-tracking",
        "team-classification",
        "player-detection",
    ):
        assert (
            client.post(
                f"/api/matches/{tracks.match_id}/jobs/{stage}", headers=coach_headers
            ).status_code
            == 409
        )


def test_rq_coordinate_delivery_contains_only_ids(settings, monkeypatch):
    queue = RQJobQueue(settings)
    persist = Mock()
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_coordinate_mapping(12, 3, "coordinate-attempt")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.coordinate_mapping.map_coordinates",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert job.timeout == settings.detection_job_timeout_seconds
    queue.close()


def test_migration_preserves_populated_phase8_assignments_and_constraints(
    engine, tracks, settings
):
    track_path = settings.storage_dir / tracks.artifact_relative_path
    track_bytes = track_path.read_bytes()
    with create_session_factory(engine)() as session:
        session.add(
            TrackTeamAssignment(
                match_id=tracks.match_id,
                tracking_job_id=tracks.id,
                tracking_version="a" * 64,
                track_id=3,
                automatic_team="team_a",
                automatic_confidence=0.8,
                manual_team="unknown",
                updated_by_user_id=tracks.created_by_user_id,
            )
        )
        session.commit()
    with engine.begin() as connection:
        config = migration_config(connection)
        assignment = (
            connection.execute(text("SELECT * FROM track_team_assignments"))
            .mappings()
            .all()
        )
        command.downgrade(config, "0007_team_classification")
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
        # Fixed table names, complete records and stable order: exercise the
        # populated 0007 schema, including tracking provenance and manual overrides.
        before = {
            table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))
            .mappings()
            .all()
            for table in tables
        }
        assert all(before.values()), "Each migration fixture table must be populated"
        # The historical schema intentionally lacks later provenance columns.
        # Compare every legacy value now and the complete row after returning head.
        assert before["track_team_assignments"] == [
            {key: row[key] for key in before["track_team_assignments"][0]}
            for row in assignment
        ]
        assert assignment[0]["manual_team"] == "unknown"
        assert any(row["tracking_summary"] for row in before["processing_jobs"])
        command.upgrade(config, "0008_coordinate_mapping")
        for table, original in before.items():
            current = (
                connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))
                .mappings()
                .all()
            )
            assert [
                {key: row[key] for key in original[0]} for row in current
            ] == original, table
        assert track_path.read_bytes() == track_bytes
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0008_coordinate_mapping"
        )
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert "coordinate_summary" in {
            c["name"] for c in inspect(connection).get_columns("processing_jobs")
        }
        command.upgrade(config, "head")
        command.check(config)
        assert (
            connection.execute(text("SELECT * FROM track_team_assignments"))
            .mappings()
            .all()
        ) == assignment
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE track_team_assignments SET tracking_job_id = 999999")
            )


def test_downgrade_refuses_to_remove_coordinate_history(
    client, tracks, coach_headers, queue, engine
):
    job = enqueue(client, tracks.match_id, coach_headers)
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="coordinate mapping jobs"):
            command.downgrade(migration_config(connection), "0007_team_classification")
        assert (
            connection.scalar(
                text("SELECT job_type FROM processing_jobs WHERE id = :id"),
                {"id": job["id"]},
            )
            == "coordinate_mapping"
        )
        command.upgrade(migration_config(connection), "head")
    assert test_jobs.persisted_job(engine, job["id"]).job_type == "coordinate_mapping"
