"""Job lifecycle with synthetic clips and an injectable queue; no Redis needed."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import test_football
from conftest import migration_config
from redis.exceptions import ConnectionError as RedisConnectionError
from rq.serializers import JSONSerializer
from sqlalchemy import inspect, text, update
from sqlalchemy.exc import IntegrityError
from test_football import role_account

from alembic import command
from app.auth.tokens import create_access_token
from app.core.jobs import JobStatus
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.media import MatchVideo, ProcessingJob
from app.services.domain_common import DomainError
from app.services.video_inspection import inspect_video
from app.workers import video_preparation
from app.workers.queue import QueueUnavailable, RQJobQueue, get_job_queue

domain = test_football.domain


class RecordingQueue:
    def __init__(self):
        self.calls: list[tuple[int, int, str]] = []
        self.unavailable = False

    def enqueue_video_preparation(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        if self.unavailable:
            raise QueueUnavailable("Redis is unavailable")
        self.calls.append((job_id, attempt, rq_job_id))


@pytest.fixture
def queue(client):
    recording_queue = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: recording_queue
    yield recording_queue
    client.app.dependency_overrides.pop(get_job_queue, None)


@pytest.fixture
def source_video(domain, session, settings, tmp_path, admin, monkeypatch):
    settings.storage_dir = tmp_path / "media"
    settings.ffprobe_path = str(tmp_path / "ffprobe-not-installed")
    match_id = domain["matches"][0]["id"]
    path = settings.storage_dir / f"raw/matches/{match_id}/synthetic.mp4"
    path.parent.mkdir(parents=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    assert writer.isOpened()
    for value in (10, 40, 80, 160):
        writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
    writer.release()
    video = MatchVideo(
        match_id=match_id,
        original_filename="synthetic.mp4",
        stored_filename=path.name,
        relative_storage_path=path.relative_to(settings.storage_dir).as_posix(),
        file_size_bytes=path.stat().st_size,
        mime_type="video/mp4",
        width=64,
        height=48,
        fps=10,
        duration_seconds=0.4,
        frame_count=4,
        uploaded_by_user_id=admin.id,
    )
    session.add(video)
    session.commit()
    monkeypatch.setattr(video_preparation, "get_settings", lambda: settings)
    return video, path


def create_job(client, source_video, headers):
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/video-preparation",
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def persisted_job(engine, job_id):
    with create_session_factory(engine)() as session:
        return session.get(ProcessingJob, job_id)


def fail_job(engine, job_id):
    with create_session_factory(engine)() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(
                status=JobStatus.FAILED,
                error_message="Synthetic failed attempt",
                current_stage="failed",
                progress_percent=25,
                started_at=utc_now(),
                finished_at=utc_now(),
            )
        )
        session.commit()


def test_create_durable_queued_job_and_safe_paginated_reads(
    client, source_video, coach_headers, queue, engine
):
    job = create_job(client, source_video, coach_headers)
    assert job["status"] == "queued" and job["progress_percent"] == 0
    assert job["started_at"] is None and job["finished_at"] is None
    assert job["video_id"] == source_video[0].id
    assert queue.calls[0][:2] == (job["id"], 0)
    assert all(isinstance(value, int) for value in queue.calls[0][:2])
    assert persisted_job(engine, job["id"]).rq_job_id == queue.calls[0][2]
    response = client.get(f"/api/jobs/{job['id']}", headers=coach_headers)
    assert response.json() == job
    page = client.get(
        f"/api/matches/{job['match_id']}/jobs?limit=1", headers=coach_headers
    ).json()
    assert page["total"] == 1 and page["items"] == [job]
    assert not {
        "attempt",
        "rq_job_id",
        "relative_storage_path",
        "stored_filename",
    }.intersection(job)
    duplicate = client.post(
        f"/api/matches/{job['match_id']}/jobs/video-preparation", headers=coach_headers
    )
    assert duplicate.status_code == 409 and len(queue.calls) == 1


def test_missing_video_and_archived_match_cannot_queue(
    client, domain, coach_headers, queue
):
    match_id = domain["matches"][0]["id"]
    url = f"/api/matches/{match_id}/jobs/video-preparation"
    assert client.post(url, headers=coach_headers).status_code == 409
    client.patch(
        f"/api/matches/{match_id}", headers=coach_headers, json={"is_archived": True}
    )
    assert client.post(url, headers=coach_headers).status_code == 409
    assert not queue.calls


def test_redis_failure_is_durable_failed_503_without_synchronous_work(
    client, source_video, coach_headers, queue, engine, monkeypatch
):
    queue.unavailable = True
    worker = Mock(side_effect=AssertionError("API must not execute worker"))
    monkeypatch.setattr(video_preparation, "prepare_video", worker)
    response = client.post(
        f"/api/matches/{source_video[0].match_id}/jobs/video-preparation",
        headers=coach_headers,
    )
    assert response.status_code == 503
    page = client.get(
        f"/api/matches/{source_video[0].match_id}/jobs", headers=coach_headers
    ).json()
    job = page["items"][0]
    assert job["status"] == "failed" and job["current_stage"] == "queue_unavailable"
    assert job["finished_at"] and "queue" in job["error_message"]
    assert persisted_job(engine, job["id"]).status == "failed"
    worker.assert_not_called()


def test_worker_own_session_real_video_progress_and_warnings(
    client, source_video, coach_headers, queue, engine, monkeypatch
):
    job = create_job(client, source_video, coach_headers)
    opened_engines = []
    original_engine = video_preparation.create_database_engine

    def open_engine(url):
        worker_engine = original_engine(url)
        opened_engines.append(worker_engine)
        return worker_engine

    monkeypatch.setattr(video_preparation, "create_database_engine", open_engine)

    def inspect_with_progress(path, settings):
        running = persisted_job(engine, job["id"])
        assert running.status == "running" and running.progress_percent == 25
        assert running.current_stage == "validating_video" and running.started_at
        return inspect_video(path, settings)

    monkeypatch.setattr(video_preparation, "inspect_video", inspect_with_progress)
    video_preparation.prepare_video(job["id"], 0)
    completed = client.get(f"/api/jobs/{job['id']}", headers=coach_headers).json()
    assert completed["status"] == "completed_with_warnings"
    assert completed["progress_percent"] == 100 and completed["warning_message"]
    assert completed["error_message"] is None and completed["finished_at"].endswith("Z")
    assert opened_engines and opened_engines[0] is not engine
    with create_session_factory(engine)() as session:
        saved = session.get(MatchVideo, source_video[0].id)
        assert (saved.width, saved.height, saved.frame_count) == (64, 48, 4)
        assert saved.fps == pytest.approx(10)
        assert saved.duration_seconds == pytest.approx(0.4)


def test_completed_without_warnings_and_duplicate_delivery_are_safe(
    client, source_video, coach_headers, queue, monkeypatch
):
    job = create_job(client, source_video, coach_headers)

    def inspected(path, settings):
        return replace(inspect_video(path, settings), warning_message=None)

    spy = Mock(side_effect=inspected)
    monkeypatch.setattr(video_preparation, "inspect_video", spy)
    video_preparation.prepare_video(job["id"], 0)
    video_preparation.prepare_video(job["id"], 0)
    assert spy.call_count == 1
    result = client.get(f"/api/jobs/{job['id']}", headers=coach_headers).json()
    assert result["status"] == "completed" and result["warning_message"] is None


def test_worker_error_is_persisted_without_internal_details(
    client, source_video, coach_headers, queue, monkeypatch
):
    job = create_job(client, source_video, coach_headers)
    monkeypatch.setattr(
        video_preparation,
        "inspect_video",
        Mock(side_effect=RuntimeError("private /internal/decoder/path")),
    )
    with pytest.raises(RuntimeError):
        video_preparation.prepare_video(job["id"], 0)
    response = client.get(f"/api/jobs/{job['id']}", headers=coach_headers)
    failed = response.json()
    assert failed["status"] == "failed" and failed["finished_at"]
    assert "private" not in response.text and "Traceback" not in response.text
    assert failed["progress_percent"] == 25 and failed["error_message"]


@pytest.mark.parametrize("failure", ["missing", "size_changed", "retired"])
def test_worker_validates_source_before_inspection(
    client, source_video, coach_headers, queue, engine, failure, monkeypatch
):
    job = create_job(client, source_video, coach_headers)
    video, path = source_video
    if failure == "missing":
        path.unlink()
    elif failure == "size_changed":
        path.write_bytes(b"changed test file")
    else:
        with create_session_factory(engine)() as session:
            session.execute(
                update(MatchVideo)
                .where(MatchVideo.id == video.id)
                .values(is_active=False)
            )
            session.commit()
    inspector = Mock()
    monkeypatch.setattr(video_preparation, "inspect_video", inspector)
    with pytest.raises(DomainError):
        video_preparation.prepare_video(job["id"], 0)
    inspector.assert_not_called()
    assert persisted_job(engine, job["id"]).status == "failed"


def test_retry_resets_fields_increments_count_and_rejects_old_deliveries(
    client, source_video, coach_headers, queue, engine, monkeypatch
):
    job = create_job(client, source_video, coach_headers)
    fail_job(engine, job["id"])
    response = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert response.status_code == 202
    retried = response.json()
    assert retried["retry_count"] == 1 and retried["status"] == "queued"
    assert (
        retried["started_at"]
        is retried["finished_at"]
        is retried["error_message"]
        is None
    )
    assert retried["progress_percent"] == 0
    assert (
        queue.calls[1][:2] == (job["id"], 1) and queue.calls[0][2] != queue.calls[1][2]
    )
    assert (
        client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers).status_code
        == 409
    )
    inspector = Mock(side_effect=inspect_video)
    monkeypatch.setattr(video_preparation, "inspect_video", inspector)
    video_preparation.prepare_video(job["id"], 0)
    inspector.assert_not_called()
    assert persisted_job(engine, job["id"]).status == "queued"
    video_preparation.prepare_video(job["id"], 1)
    assert inspector.call_count == 1


def test_retry_of_replaced_source_is_rejected(
    client, source_video, coach_headers, queue, engine
):
    job = create_job(client, source_video, coach_headers)
    fail_job(engine, job["id"])
    with create_session_factory(engine)() as session:
        session.execute(
            update(MatchVideo)
            .where(MatchVideo.id == job["video_id"])
            .values(is_active=False)
        )
        session.add(
            MatchVideo(
                match_id=job["match_id"],
                original_filename="replacement.mp4",
                stored_filename="replacement.mp4",
                relative_storage_path="raw/replacement.mp4",
                file_size_bytes=99,
                mime_type="video/mp4",
                width=64,
                height=48,
                fps=10,
                duration_seconds=1,
                uploaded_by_user_id=job["created_by_user_id"],
            )
        )
        session.commit()
    response = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert response.status_code == 409 and "replaced" in response.json()["detail"]
    assert len(queue.calls) == 1


def test_rq_failure_callback_marks_active_attempt_only(
    client, source_video, coach_headers, queue, engine
):
    job = create_job(client, source_video, coach_headers)
    rq_job = SimpleNamespace(kwargs={"processing_job_id": job["id"], "attempt": 0})
    video_preparation.record_rq_failure(
        rq_job, None, RuntimeError, RuntimeError(), None
    )
    assert persisted_job(engine, job["id"]).status == "failed"
    assert (
        client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers).status_code
        == 202
    )
    video_preparation.record_workhorse_failure(rq_job, 1, 1, None)
    assert persisted_job(engine, job["id"]).status == "queued"


@pytest.mark.parametrize("role", ["analyst", "club_management", "player"])
def test_job_permissions_by_role(
    client, domain, source_video, admin_headers, queue, role
):
    job = create_job(client, source_video, admin_headers)
    _, headers = role_account(client, domain, role)
    expected_read = 403 if role == "player" else 200
    assert (
        client.get(f"/api/jobs/{job['id']}", headers=headers).status_code
        == expected_read
    )
    assert (
        client.get(f"/api/matches/{job['match_id']}/jobs", headers=headers).status_code
        == expected_read
    )
    assert (
        client.get(
            f"/api/matches/{job['match_id']}/jobs/video-preparation", headers=headers
        ).status_code
        == expected_read
    )
    expected_write = 409 if role == "analyst" else 403
    assert (
        client.post(f"/api/jobs/{job['id']}/retry", headers=headers).status_code
        == expected_write
    )
    assert (
        client.post(
            f"/api/matches/{job['match_id']}/jobs/video-preparation", headers=headers
        ).status_code
        == expected_write
    )


def test_foreign_club_jobs_and_anonymous_are_inaccessible(
    client, domain, source_video, admin_headers, queue, settings
):
    job = create_job(client, source_video, admin_headers)
    from conftest import TEST_PASSWORD

    outside = domain["post"](
        "users",
        {
            "email": "outside-coach@example.com",
            "full_name": "Outside Coach",
            "password": TEST_PASSWORD,
            "roles": ["coach"],
        },
    )
    domain["post"](
        f"clubs/{domain['clubs'][1]['id']}/members", {"user_id": outside["id"]}
    )
    headers = {
        "Authorization": f"Bearer {create_access_token(outside['id'], settings)}"
    }
    for method, path in (
        ("GET", f"jobs/{job['id']}"),
        ("POST", f"jobs/{job['id']}/retry"),
        ("GET", f"matches/{job['match_id']}/jobs"),
        ("GET", f"matches/{job['match_id']}/jobs/video-preparation"),
        ("POST", f"matches/{job['match_id']}/jobs/video-preparation"),
    ):
        assert (
            client.request(method, f"/api/{path}", headers=headers).status_code == 404
        )
        assert client.request(method, f"/api/{path}").status_code == 401


def test_rq_serialization_and_unavailable_boundary(settings, monkeypatch):
    queue = RQJobQueue(settings)
    enqueue = Mock()
    monkeypatch.setattr(queue.queue, "enqueue", enqueue)
    queue.enqueue_video_preparation(12, 3, "safe-rq-id")
    args, options = enqueue.call_args
    assert args == ("app.workers.video_preparation.prepare_video",)
    assert options["kwargs"] == {"processing_job_id": 12, "attempt": 3}
    assert options["job_id"] == "safe-rq-id" and options["unique"] is True
    assert (
        options["on_failure"].name == "app.workers.video_preparation.record_rq_failure"
    )
    enqueue.side_effect = RedisConnectionError("offline")
    with pytest.raises(QueueUnavailable):
        queue.enqueue_video_preparation(12, 3, "safe-rq-id")
    queue.close()


def test_rq_builds_real_json_job_without_contacting_redis(settings, monkeypatch):
    queue = RQJobQueue(settings)
    persist = Mock()
    monkeypatch.setattr(queue.queue, "enqueue_job", persist)
    queue.enqueue_video_preparation(12, 3, "safe-rq-id")
    job = persist.call_args.args[0]
    assert JSONSerializer.loads(job.data) == [
        "app.workers.video_preparation.prepare_video",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert job.failure_callback is video_preparation.record_rq_failure
    assert job.timeout == settings.rq_job_timeout_seconds
    assert job.id == "safe-rq-id"
    queue.close()


def test_retry_stays_on_first_page_ahead_of_newer_terminal_jobs(
    client, source_video, coach_headers, queue, engine
):
    older = create_job(client, source_video, coach_headers)
    fail_job(engine, older["id"])
    newer = create_job(client, source_video, coach_headers)
    fail_job(engine, newer["id"])
    assert (
        client.post(f"/api/jobs/{older['id']}/retry", headers=coach_headers).status_code
        == 202
    )
    first_page = client.get(
        f"/api/matches/{older['match_id']}/jobs?limit=1", headers=coach_headers
    ).json()
    assert first_page["total"] == 2
    assert first_page["items"][0]["id"] == older["id"]
    assert first_page["items"][0]["status"] == "queued"


@pytest.mark.parametrize(
    "invalid", ["progress", "status", "type", "duplicate", "video_match"]
)
def test_job_database_constraints(
    client, domain, source_video, coach_headers, queue, engine, invalid
):
    job = create_job(client, source_video, coach_headers)
    values = dict(
        match_id=job["match_id"],
        video_id=job["video_id"],
        job_type="video_preparation",
        status="failed",
        progress_percent=0,
        current_stage="test",
        created_by_user_id=job["created_by_user_id"],
    )
    changes = {
        "progress": {"progress_percent": 101},
        "status": {"status": "invented"},
        "type": {"job_type": "full_analysis"},
        "duplicate": {"status": "queued"},
        "video_match": {"match_id": domain["matches"][1]["id"]},
    }
    with create_session_factory(engine)() as session:
        session.add(ProcessingJob(**(values | changes[invalid])))
        with pytest.raises(IntegrityError):
            session.commit()


def test_phase3_upgrade_preserves_domain_and_auth(
    engine, domain, client, admin_headers
):
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0002_clubs_teams_players_matches")
        previous = {
            table: connection.execute(text(f"SELECT * FROM {table}")).all()
            for table in (
                "users",
                "roles",
                "user_roles",
                "clubs",
                "club_memberships",
                "teams",
                "players",
                "squad_memberships",
                "matches",
            )
        }
        command.upgrade(config, "head")
        assert {"match_videos", "processing_jobs"}.issubset(
            inspect(connection).get_table_names()
        )
        for table, rows in previous.items():
            assert connection.execute(text(f"SELECT * FROM {table}")).all() == rows
        command.check(config)
    response = client.get(
        f"/api/matches/{domain['matches'][0]['id']}", headers=admin_headers
    )
    assert response.status_code == 200 and response.json() == domain["matches"][0]


@pytest.mark.parametrize(
    "status", ["queued", "running", "completed", "completed_with_warnings"]
)
def test_preparation_duplicate_never_requeues_current_video(
    client, source_video, coach_headers, queue, engine, status
):
    job = create_job(client, source_video, coach_headers)
    with create_session_factory(engine)() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job["id"])
            .values(status=status)
        )
        session.commit()
    url = f"/api/matches/{job['match_id']}/jobs/video-preparation"
    current = client.get(url, headers=coach_headers)
    assert current.status_code == 200 and current.json()["id"] == job["id"]
    duplicate = client.post(url, headers=coach_headers)
    if status in ("queued", "running"):
        assert duplicate.status_code == 409
    else:
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == job["id"]
        assert duplicate.json()["status"] == status
    assert len(queue.calls) == 1
    assert (
        client.get(
            f"/api/matches/{job['match_id']}/jobs", headers=coach_headers
        ).json()["total"]
        == 1
    )


def test_successful_preparation_is_reused_and_failed_history_cannot_retry_it(
    client, source_video, coach_headers, queue, engine
):
    failed = create_job(client, source_video, coach_headers)
    fail_job(engine, failed["id"])
    current = create_job(client, source_video, coach_headers)
    with create_session_factory(engine)() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == current["id"])
            .values(status="completed", progress_percent=100)
        )
        session.commit()
    assert (
        client.post(
            f"/api/jobs/{failed['id']}/retry", headers=coach_headers
        ).status_code
        == 409
    )
    assert create_job(client, source_video, coach_headers)["id"] == current["id"]
    history = client.get(
        f"/api/matches/{current['match_id']}/jobs", headers=coach_headers
    ).json()
    assert history["total"] == 2
    assert {row["id"] for row in history["items"]} == {failed["id"], current["id"]}
    assert len(queue.calls) == 2


def test_replacement_resets_preparation_without_removing_history(
    client, source_video, coach_headers, queue, engine
):
    old = create_job(client, source_video, coach_headers)
    with create_session_factory(engine)() as session:
        session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == old["id"])
            .values(status="completed")
        )
        video = session.get(MatchVideo, old["video_id"])
        video.is_active = False
        session.flush()
        replacement = MatchVideo(
            match_id=video.match_id,
            original_filename="new.mp4",
            stored_filename="new.mp4",
            relative_storage_path="raw/new.mp4",
            file_size_bytes=99,
            mime_type="video/mp4",
            width=64,
            height=48,
            fps=10,
            duration_seconds=1,
            uploaded_by_user_id=old["created_by_user_id"],
        )
        session.add(replacement)
        session.commit()
        replacement_id = replacement.id
    url = f"/api/matches/{old['match_id']}/jobs/video-preparation"
    assert client.get(url, headers=coach_headers).json() is None
    new = client.post(url, headers=coach_headers)
    assert new.status_code == 202 and new.json()["video_id"] == replacement_id
    assert new.json()["id"] != old["id"]
    assert client.get(url, headers=coach_headers).json()["id"] == new.json()["id"]
    assert (
        client.get(f"/api/jobs/{old['id']}", headers=coach_headers).json()["status"]
        == "completed"
    )
    assert len(queue.calls) == 2
