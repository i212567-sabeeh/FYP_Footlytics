"""Saved-coordinate job integration; queue injection and no upstream CV execution."""

import csv
from unittest.mock import Mock

import pytest
import test_coordinate_jobs
import test_jobs
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import inspect, text, update
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.auth.tokens import create_access_token
from app.cv import coordinate_pipeline, homography, trajectory_pipeline
from app.cv.coordinate_rows import TrajectoryError
from app.cv.player_position import PitchPosition
from app.cv.tracking_rows import TrackObservation
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.media import MatchVideo, ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.schemas.coordinates import CoordinateSummary
from app.services.coordinate_artifacts import CoordinateArtifact
from app.services.coordinate_inputs import current_mapping_inputs
from app.services.domain_common import DomainError
from app.services.tracking_artifacts import COLUMNS as TRACK_COLUMNS
from app.services.tracking_inputs import file_version
from app.services.trajectory_artifacts import COLUMNS, TrajectoryArtifact
from app.workers import trajectory_cleaning as worker
from app.workers.queue import RQJobQueue, get_job_queue

domain = test_coordinate_jobs.domain
source_video = test_coordinate_jobs.source_video
calibrated = test_coordinate_jobs.calibrated
detections = test_coordinate_jobs.detections
tracks = test_coordinate_jobs.tracks
upstream_queue = test_coordinate_jobs.queue


@pytest.fixture
def coordinates(tracks, settings, session, request):
    path = settings.storage_dir / tracks.artifact_relative_path
    variant = getattr(request, "param", None)
    if variant in ("empty", "inside", "outside"):
        rows = (
            []
            if variant == "empty"
            else [
                row
                for row in test_coordinate_jobs.rows_at(path)
                if row["track_id"] == ("7" if variant == "inside" else "3")
            ]
        )
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=TRACK_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        tracks.tracking_summary = {
            **tracks.tracking_summary,
            "total_track_rows": len(rows),
            "unique_tracks": int(bool(rows)),
        }
        session.commit()
    from app.models.football import Match

    inputs = current_mapping_inputs(
        session, session.get(Match, tracks.match_id), settings
    )
    job = ProcessingJob(
        match_id=tracks.match_id,
        video_id=tracks.video_id,
        job_type="coordinate_mapping",
        status="completed",
        progress_percent=100,
        current_stage="completed",
        created_by_user_id=tracks.created_by_user_id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        tracking_snapshot=inputs.source.version,
        calibration_snapshot=inputs.calibration,
    )
    session.add(job)
    session.flush()
    count = inside = 0
    frames, ids = [], set()
    with CoordinateArtifact(
        settings, job.match_id, job.video_id, job.id, 0
    ) as artifact:
        for data in test_coordinate_jobs.rows_at(path):
            box = tuple(float(data[k]) for k in ("x1", "y1", "x2", "y2"))
            frame = int(data["frame_number"])
            track_id = int(data["track_id"])
            pixel_x, pixel_y = (box[0] + box[2]) / 2, box[3]
            # Explicit synthetic Phase 9 fixture; do not execute coordinate mapping.
            x, y = 0.5 * pixel_x - 10, 0.5 * pixel_y
            valid = 0 <= x <= 30 and 0 <= y <= 20
            artifact.write_position(
                TrackObservation(
                    frame,
                    float(data["timestamp_seconds"]),
                    track_id,
                    box,
                    float(data["confidence"]),
                ),
                PitchPosition(pixel_x, pixel_y, x, y, valid),
            )
            count += 1
            inside += valid
            frames.append(frame)
            ids.add(track_id)
        data = CoordinateSummary(
            total_rows=count,
            valid_mapped_rows=count,
            skipped_invalid_boxes=0,
            inside_pitch_rows=inside,
            outside_pitch_rows=count - inside,
            unique_tracks=len(ids),
            first_frame=min(frames, default=None),
            last_frame=max(frames, default=None),
            tracking_job_id=tracks.id,
            tracking_attempt=tracks.attempt,
            calibration_id=inputs.calibration["id"],
            calibration_updated_at=inputs.calibration["updated_at"],
            pitch_length_metres=30,
            pitch_width_metres=20,
            bounds_tolerance_metres=1e-6,
        )
        job.artifact_relative_path = artifact.publish()
        job.coordinate_summary = {
            **data.model_dump(mode="json"),
            "artifact_version": file_version(artifact.path),
        }
        session.commit()
        artifact.keep()
    return job


class RecordingQueue(test_coordinate_jobs.RecordingQueue):
    def enqueue_trajectory_cleaning(self, job_id, attempt, rq_job_id):
        self.enqueue_coordinate_mapping(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, settings, monkeypatch, upstream_queue):
    instance = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: instance
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(
        coordinate_pipeline,
        "map_tracking",
        Mock(side_effect=AssertionError("Coordinate mapping executed")),
    )
    monkeypatch.setattr(
        homography,
        "transform_points",
        Mock(side_effect=AssertionError("Mapping executed")),
    )
    yield instance


def enqueue(client, match_id, headers):
    response = client.post(
        f"/api/matches/{match_id}/jobs/trajectory-cleaning", headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def summary(client, match_id, headers):
    return client.get(f"/api/matches/{match_id}/trajectories/summary", headers=headers)


def test_worker_preserves_raw_artifact_and_publishes_auditable_rows_and_summary(
    client,
    coordinates,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    path = settings.storage_dir / coordinates.artifact_relative_path
    raw_bytes = path.read_bytes()
    monkeypatch.setattr(trajectory_pipeline, "PROGRESS_ROWS", 2)
    state = Mock(wraps=worker._running)
    monkeypatch.setattr(worker, "_running", state)
    job = enqueue(client, coordinates.match_id, coach_headers)
    assert (
        job["job_type"] == "trajectory_cleaning" and job["trajectory_summary"] is None
    )
    assert summary(client, coordinates.match_id, coach_headers).status_code == 409
    assert queue.calls[0][:2] == (job["id"], 0)
    worker.clean_trajectories(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed_with_warnings" and stored.progress_percent == 100
    output = settings.storage_dir / stored.artifact_relative_path
    assert output != path and f"/jobs/{job['id']}/attempt-0-" in str(output)
    rows = test_coordinate_jobs.rows_at(output)
    assert tuple(rows[0]) == COLUMNS and len(rows) == 6
    assert [int(r["track_id"]) for r in rows] == [3, 3, 3, 7, 7, 7]
    assert all(
        r["usable"] == "false"
        and r["clean_pitch_x"] == ""
        and r["clean_pitch_y"] == ""
        and r["status"] == "outside_pitch"
        for r in rows[:3]
    )
    assert [float(r["raw_pitch_x"]) for r in rows[:3]] == [-2.5, -2, -1]
    assert all(r["usable"] == "true" and r["segment_id"] == "1" for r in rows[3:])
    assert all(r["is_interpolated"] == "false" for r in rows)
    response = summary(client, coordinates.match_id, coach_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["source_rows"], data["usable_rows"], data["rejected_rows"]) == (
        6,
        3,
        3,
    )
    assert data["outside_pitch_rows"] == 3 and data["jump_outlier_rows"] == 0
    assert data["unique_tracks"] == 2 and data["segments"] == 1
    assert (data["first_frame"], data["last_frame"]) == (0, 3)
    assert (
        data["coordinate_job_id"] == coordinates.id and data["interpolated_rows"] == 0
    )
    assert [
        c.kwargs["progress_percent"]
        for c in state.call_args_list
        if "progress_percent" in c.kwargs
    ] == [40, 59, 79, 99, 100]
    assert [
        c.kwargs["current_stage"]
        for c in state.call_args_list
        if "current_stage" in c.kwargs
    ] == [
        "loading_coordinates",
        "cleaning_tracks",
        "cleaning_tracks",
        "cleaning_tracks",
        "writing_trajectories",
        "completed",
    ]
    public = client.get(f"/api/jobs/{job['id']}", headers=coach_headers)
    assert not {"coordinate_snapshot", "artifact_relative_path"}.intersection(
        public.json()
    )
    assert "artifact_version" not in public.json()["trajectory_summary"]
    assert str(settings.storage_dir) not in response.text + public.text
    assert path.read_bytes() == raw_bytes
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert not list(settings.storage_dir.rglob("trajectory-*"))
    worker.clean_trajectories(job["id"], 0)
    assert test_coordinate_jobs.rows_at(output) == rows


@pytest.mark.parametrize("coordinates", ["empty"], indirect=True)
def test_empty_coordinates_publish_header_only_with_warning(
    client,
    coordinates,
    settings,
    engine,
    coach_headers,
    queue,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    worker.clean_trajectories(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed_with_warnings"
    assert not test_coordinate_jobs.rows_at(
        settings.storage_dir / stored.artifact_relative_path
    )
    data = summary(client, coordinates.match_id, coach_headers).json()
    assert data["source_rows"] == data["usable_rows"] == data["segments"] == 0
    assert data["first_frame"] is data["last_frame"] is None


@pytest.mark.parametrize(
    "coordinates,usable,status",
    [
        ("inside", 3, "completed"),
        ("outside", 0, "completed_with_warnings"),
    ],
    indirect=["coordinates"],
)
def test_all_usable_and_all_rejected_results_have_correct_terminal_state(
    client,
    coordinates,
    engine,
    coach_headers,
    queue,
    usable,
    status,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    worker.clean_trajectories(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == status
    data = summary(client, coordinates.match_id, coach_headers).json()
    assert data["source_rows"] == 3 and data["usable_rows"] == usable
    assert data["rejected_rows"] == 3 - usable and data["segments"] == int(bool(usable))


def test_missing_coordinate_result_never_starts_upstream_jobs(
    client,
    tracks,
    coach_headers,
    queue,
):
    response = client.post(
        f"/api/matches/{tracks.match_id}/jobs/trajectory-cleaning",
        headers=coach_headers,
    )
    assert response.status_code == 409 and "coordinate" in response.text
    assert not queue.calls


@pytest.mark.parametrize(
    "fault", ["file", "calibration", "tracking", "video", "summary"]
)
def test_missing_or_stale_coordinates_rejected_before_queueing(
    client,
    coordinates,
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
        (settings.storage_dir / coordinates.artifact_relative_path).unlink()
    elif fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "tracking":
        tracks.updated_at = utc_now()
    elif fault == "video":
        source_video[0].is_active = False
    else:
        coordinates.coordinate_summary = {
            **coordinates.coordinate_summary,
            "valid_mapped_rows": 999,
        }
    session.commit()
    response = client.post(
        f"/api/matches/{coordinates.match_id}/jobs/trajectory-cleaning",
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
        "new_coordinates",
        "file",
    ],
)
def test_upstream_changes_during_cleaning_prevent_publication(
    client,
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
    job = enqueue(client, coordinates.match_id, coach_headers)
    actual = TrajectoryArtifact.write_observation
    changed = False

    def mutate(artifact, point):
        nonlocal changed
        actual(artifact, point)
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
            elif fault in ("tracking", "coordinates"):
                identity = tracks.id if fault == "tracking" else coordinates.id
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == identity)
                    .values(updated_at=utc_now())
                )
            elif fault == "file":
                path = settings.storage_dir / coordinates.artifact_relative_path
                path.write_bytes(path.read_bytes().replace(b"12.5", b"12.4"))
            else:
                newer = ProcessingJob(
                    match_id=coordinates.match_id,
                    video_id=coordinates.video_id,
                    job_type="coordinate_mapping",
                    status="completed",
                    progress_percent=100,
                    current_stage="completed",
                    created_by_user_id=coordinates.created_by_user_id,
                    attempt=0,
                    retry_count=0,
                    finished_at=utc_now(),
                    tracking_snapshot=coordinates.tracking_snapshot,
                    calibration_snapshot=coordinates.calibration_snapshot,
                )
                session.add(newer)
                session.flush()
                relative = coordinates.artifact_relative_path.replace(
                    f"/jobs/{coordinates.id}/", f"/jobs/{newer.id}/"
                )
                path = settings.storage_dir / relative
                path.parent.mkdir(parents=True)
                path.write_bytes(
                    (
                        settings.storage_dir / coordinates.artifact_relative_path
                    ).read_bytes()
                )
                newer.artifact_relative_path = relative
                newer.coordinate_summary = {
                    **coordinates.coordinate_summary,
                    "artifact_version": file_version(path),
                }
            session.commit()

    monkeypatch.setattr(TrajectoryArtifact, "write_observation", mutate)
    publish = Mock(wraps=TrajectoryArtifact.publish)
    monkeypatch.setattr(TrajectoryArtifact, "publish", publish)
    with pytest.raises((DomainError, TrajectoryError)):
        worker.clean_trajectories(job["id"], 0)
    publish.assert_not_called()
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "failed" and stored.artifact_relative_path is None
    assert (
        stored.trajectory_summary is None
        and str(settings.storage_dir) not in stored.error_message
    )
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert not list(settings.storage_dir.rglob("trajectory-*"))


def test_team_override_during_cleaning_does_not_invalidate_output(
    client,
    coordinates,
    tracks,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    actual = TrajectoryArtifact.write_observation
    changed = False

    def correct_team(artifact, point):
        nonlocal changed
        actual(artifact, point)
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

    monkeypatch.setattr(TrajectoryArtifact, "write_observation", correct_team)
    worker.clean_trajectories(job["id"], 0)
    assert summary(client, coordinates.match_id, coach_headers).status_code == 200


def test_failed_attempt_retry_and_stale_delivery_preserve_previous_artifact(
    client,
    coordinates,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    first = enqueue(client, coordinates.match_id, coach_headers)
    worker.clean_trajectories(first["id"], 0)
    old = test_jobs.persisted_job(engine, first["id"])
    old_path = settings.storage_dir / old.artifact_relative_path
    original = old_path.read_bytes()
    second = enqueue(client, coordinates.match_id, coach_headers)
    real_publish = TrajectoryArtifact.publish
    with monkeypatch.context() as patch:

        def fail_after_publish(artifact):
            real_publish(artifact)
            raise OSError("/private/trajectory/storage")

        patch.setattr(TrajectoryArtifact, "publish", fail_after_publish)
        with pytest.raises(OSError):
            worker.clean_trajectories(second["id"], 0)
    failed = test_jobs.persisted_job(engine, second["id"])
    assert failed.status == "failed" and "/private" not in failed.error_message
    assert failed.artifact_relative_path is None and old_path.read_bytes() == original
    assert (
        summary(client, coordinates.match_id, coach_headers).json()["job_id"]
        == first["id"]
    )
    assert (
        client.post(
            f"/api/jobs/{second['id']}/retry", headers=coach_headers
        ).status_code
        == 202
    )
    worker.clean_trajectories(second["id"], 0)
    assert test_jobs.persisted_job(engine, second["id"]).status == "queued"
    with monkeypatch.context() as patch:
        patch.setattr(TrajectoryArtifact, "publish", fail_after_publish)
        with pytest.raises(OSError):
            worker.clean_trajectories(second["id"], 1)
    assert old_path.read_bytes() == original
    assert (
        summary(client, coordinates.match_id, coach_headers).json()["job_id"]
        == first["id"]
    )
    assert (
        client.post(
            f"/api/jobs/{second['id']}/retry", headers=coach_headers
        ).status_code
        == 202
    )
    worker.clean_trajectories(second["id"], 1)
    assert test_jobs.persisted_job(engine, second["id"]).status == "queued"
    worker.clean_trajectories(second["id"], 2)
    latest = test_jobs.persisted_job(engine, second["id"])
    assert "/attempt-2-" in latest.artifact_relative_path
    assert latest.artifact_relative_path != old.artifact_relative_path
    assert (
        summary(client, coordinates.match_id, coach_headers).json()["job_id"]
        == second["id"]
    )
    assert old_path.read_bytes() == original
    assert not list(settings.storage_dir.rglob("*.partial"))


def test_source_file_changed_during_publication_removes_uncommitted_output(
    client,
    coordinates,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    real_publish = TrajectoryArtifact.publish

    def replace_source(artifact):
        relative = real_publish(artifact)
        path = settings.storage_dir / coordinates.artifact_relative_path
        path.write_bytes(path.read_bytes().replace(b"12.5", b"12.4"))
        return relative

    monkeypatch.setattr(TrajectoryArtifact, "publish", replace_source)
    with pytest.raises(DomainError):
        worker.clean_trajectories(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "failed" and stored.artifact_relative_path is None
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 3
    assert not list(settings.storage_dir.rglob("*.partial"))


def test_superseded_attempt_cannot_publish(
    client,
    coordinates,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    actual = TrajectoryArtifact.write_observation
    changed = False

    def supersede(artifact, point):
        nonlocal changed
        actual(artifact, point)
        if not changed:
            changed = True
            with create_session_factory(engine)() as session:
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == job["id"])
                    .values(attempt=1, status="queued")
                )
                session.commit()

    monkeypatch.setattr(TrajectoryArtifact, "write_observation", supersede)
    worker.clean_trajectories(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "queued" and stored.attempt == 1
    assert stored.artifact_relative_path is None
    assert len(list(settings.storage_dir.rglob("*.csv"))) == 3
    assert not list(settings.storage_dir.rglob("*.partial"))


@pytest.mark.parametrize("fault", ["coordinates", "output", "summary"])
def test_stale_or_damaged_results_are_not_returned_as_current(
    client,
    coordinates,
    settings,
    session,
    coach_headers,
    queue,
    fault,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    worker.clean_trajectories(job["id"], 0)
    if fault == "coordinates":
        coordinates.updated_at = utc_now()
    else:
        stored = session.get(ProcessingJob, job["id"])
        if fault == "summary":
            stored.trajectory_summary = {
                **stored.trajectory_summary,
                "usable_rows": 999,
            }
        else:
            path = settings.storage_dir / stored.artifact_relative_path
            path.write_text(path.read_text().replace("12.5", "12.4"), encoding="utf-8")
    session.commit()
    assert summary(client, coordinates.match_id, coach_headers).status_code == 409


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
    client, coordinates, coach_headers, queue, domain, settings, role, read, write
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    worker.clean_trajectories(job["id"], 0)
    account = domain["post"](
        "users",
        {
            "email": f"trajectories-{role}@example.com",
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
    assert summary(client, coordinates.match_id, headers).status_code == read
    assert (
        client.post(
            f"/api/matches/{coordinates.match_id}/jobs/trajectory-cleaning",
            headers=headers,
        ).status_code
        == write
    )


def test_cross_club_and_anonymous_denied(client, domain, coach_headers, queue):
    match_id = domain["matches"][1]["id"]
    for headers, status in ((coach_headers, 404), ({}, 401)):
        assert summary(client, match_id, headers).status_code == status
        assert (
            client.post(
                f"/api/matches/{match_id}/jobs/trajectory-cleaning", headers=headers
            ).status_code
            == status
        )
    assert not queue.calls


@pytest.mark.parametrize("match_id", [0, -1, "bad", "1.5", 2**63])
def test_malformed_ids_do_not_enqueue(client, coach_headers, queue, match_id):
    assert summary(client, match_id, coach_headers).status_code == 422
    assert (
        client.post(
            f"/api/matches/{match_id}/jobs/trajectory-cleaning", headers=coach_headers
        ).status_code
        == 422
    )
    assert not queue.calls


def test_queue_failure_and_duplicate_active_job_protection(
    client,
    coordinates,
    engine,
    coach_headers,
    queue,
):
    queue.unavailable = True
    assert (
        client.post(
            f"/api/matches/{coordinates.match_id}/jobs/trajectory-cleaning",
            headers=coach_headers,
        ).status_code
        == 503
    )
    queue.unavailable = False
    job = enqueue(client, coordinates.match_id, coach_headers)
    assert (
        client.post(
            f"/api/matches/{coordinates.match_id}/jobs/trajectory-cleaning",
            headers=coach_headers,
        ).status_code
        == 409
    )
    worker.clean_trajectories(job["id"], 0)
    assert (
        test_jobs.persisted_job(engine, job["id"]).status == "completed_with_warnings"
    )


def test_rq_delivery_contains_only_ids_and_uses_existing_queue(settings, monkeypatch):
    queue = RQJobQueue(settings)
    persist = Mock(side_effect=lambda job, *_args, **_kwargs: job)
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_trajectory_cleaning(12, 3, "trajectory-attempt")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.trajectory_cleaning.clean_trajectories",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert job.timeout == settings.detection_job_timeout_seconds
    queue.close()


def test_populated_0008_upgrade_preserves_all_records_and_manual_overrides(
    engine,
    coordinates,
    tracks,
    settings,
):
    raw = settings.storage_dir / coordinates.artifact_relative_path
    original_bytes = raw.read_bytes()
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
        command.downgrade(config, "0008_coordinate_mapping")
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
        assert before["track_team_assignments"][0]["manual_team"] == "team_b"
        assert any(row["coordinate_summary"] for row in before["processing_jobs"])
        command.upgrade(config, "0009_trajectory_cleaning")
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
            == "0009_trajectory_cleaning"
        )
        assert {"trajectory_summary", "coordinate_snapshot"} <= {
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
    assert raw.read_bytes() == original_bytes


def test_downgrade_refuses_to_destroy_trajectory_history(
    client,
    coordinates,
    engine,
    coach_headers,
    queue,
):
    job = enqueue(client, coordinates.match_id, coach_headers)
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="trajectory cleaning jobs"):
            command.downgrade(migration_config(connection), "0008_coordinate_mapping")
        assert (
            connection.scalar(
                text("SELECT job_type FROM processing_jobs WHERE id = :id"),
                {"id": job["id"]},
            )
            == "trajectory_cleaning"
        )
        command.upgrade(migration_config(connection), "head")
    assert test_jobs.persisted_job(engine, job["id"]).job_type == "trajectory_cleaning"
