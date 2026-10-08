"""Real tiny generated clips; uploads and records only use isolated test storage."""

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import cv2
import numpy as np
import pytest
import test_football
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session
from test_football import role_account

from app.models.football import ClubMembership
from app.models.media import MatchVideo, ProcessingJob
from app.models.user import User
from app.services import upload_service
from app.services.domain_common import DomainError

domain = test_football.domain


@pytest.fixture
def clip(tmp_path: Path, settings) -> bytes:
    settings.ffprobe_path = "missing-ffprobe-for-explicit-fallback-test"
    path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    assert writer.isOpened()
    for number in range(6):
        writer.write(np.full((48, 64, 3), number * 25, dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def upload(
    client,
    domain,
    headers,
    content,
    name="fixture.mp4",
    method="POST",
    mime="video/mp4",
):
    match = domain["matches"][0]["id"]
    return client.request(
        method,
        f"/api/matches/{match}/video",
        headers=headers,
        files={"file": (name, content, mime)},
    )


def stored_files(settings):
    return [path for path in settings.storage_dir.rglob("*") if path.is_file()]


def test_real_video_upload_metadata_hash_and_protected_range(
    client, domain, coach_headers, admin_headers, settings, engine, clip
):
    path = f"/api/matches/{domain['matches'][0]['id']}/video"
    assert client.get(path, headers=coach_headers).json() is None
    result = upload(client, domain, coach_headers, clip)
    assert result.status_code == 201, result.text
    video = result.json()
    assert video["width"] == 64 and video["height"] == 48
    assert video["fps"] == pytest.approx(10)
    assert video["duration_seconds"] == pytest.approx(0.6)
    assert video["frame_count"] == 6
    assert video["file_size_bytes"] == len(clip)
    assert video["sha256"] == hashlib.sha256(clip).hexdigest()
    assert video["codec"] is None and video["container_format"] is None
    assert "OpenCV" in video["warning_message"]
    assert not {"relative_storage_path", "stored_filename"}.intersection(video)
    assert str(settings.storage_dir) not in result.text
    assert client.get(path, headers=admin_headers).json()["id"] == video["id"]
    response = client.get(
        f"{path}/file", headers={**coach_headers, "Range": "bytes=0-31"}
    )
    assert response.status_code == 206 and response.content == clip[:32]
    assert response.headers["cache-control"] == "no-store"
    assert client.get(f"{path}/file").status_code == 401
    with Session(engine) as session:
        stored = session.get(MatchVideo, video["id"])
        assert stored.relative_storage_path.startswith(
            f"raw/matches/{video['match_id']}/"
        )
        assert stored.stored_filename != "fixture.mp4"
        assert not Path(stored.relative_storage_path).is_absolute()
    assert len(stored_files(settings)) == 1


@pytest.mark.parametrize(
    "name,content,mime,status",
    [
        ("../../outside.mp4", b"bad", "video/mp4", 422),
        ("C:\\outside.mp4", b"bad", "video/mp4", 422),
        ("fixture.txt", b"bad", "text/plain", 422),
        ("fake.mp4", b"this is not a movie", "video/mp4", 422),
        ("empty.mp4", b"", "video/mp4", 422),
        ("fixture.mp4", b"bad", "text/html", 422),
    ],
)
def test_invalid_uploads_leave_no_record_or_artifact(
    client, domain, coach_headers, settings, engine, name, content, mime, status
):
    result = upload(client, domain, coach_headers, content, name, mime=mime)
    assert result.status_code == status
    assert stored_files(settings) == []
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MatchVideo)) == 0


def test_size_limit_enforced_while_parsing_without_content_length(
    client, domain, coach_headers, settings
):
    settings.max_upload_size = 8
    match = domain["matches"][0]["id"]
    boundary = "test-boundary"
    chunks = [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="a.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
        ).encode(),
        b"12345",
        b"67890",
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    result = client.post(
        f"/api/matches/{match}/video",
        headers={
            **coach_headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=iter(chunks),
    )
    assert result.status_code == 413
    assert stored_files(settings) == []


def test_wrong_fields_multiple_files_and_truncated_multipart_rejected(
    client, domain, coach_headers, clip, settings
):
    path = f"/api/matches/{domain['matches'][0]['id']}/video"
    for files in (
        [("file", ("a.mp4", clip)), ("file", ("b.mp4", clip))],
        {"other": ("a.mp4", clip)},
    ):
        assert client.post(path, headers=coach_headers, files=files).status_code == 422
    body = (
        b'--test\r\nContent-Disposition: form-data; name="file"; '
        b'filename="a.mp4"\r\n\r\n' + clip
    )
    assert (
        client.post(
            path,
            headers={
                **coach_headers,
                "Content-Type": "multipart/form-data; boundary=test",
            },
            content=body,
        ).status_code
        == 422
    )
    assert stored_files(settings) == []


def test_invalid_and_duplicate_replacement_preserve_active_source(
    client, domain, coach_headers, clip, settings
):
    initial = upload(client, domain, coach_headers, clip).json()
    assert upload(client, domain, coach_headers, clip).status_code == 409
    assert (
        upload(client, domain, coach_headers, b"corrupt", method="PUT").status_code
        == 422
    )
    assert upload(client, domain, coach_headers, clip, method="PUT").status_code == 409
    current = client.get(
        f"/api/matches/{initial['match_id']}/video", headers=coach_headers
    ).json()
    assert current["id"] == initial["id"]
    assert len(stored_files(settings)) == 1


def test_successful_replacement_retains_safe_history(
    client, domain, coach_headers, clip, settings, engine
):
    initial = upload(client, domain, coach_headers, clip).json()
    # A harmless trailing free-space box yields a distinct, still-readable MP4.
    changed = clip + b"\x00\x00\x00\x08free"
    result = upload(client, domain, coach_headers, changed, method="PUT")
    assert result.status_code == 200, result.text
    assert result.json()["id"] != initial["id"]
    with Session(engine) as session:
        rows = session.scalars(select(MatchVideo).order_by(MatchVideo.id)).all()
        assert [row.is_active for row in rows] == [False, True]
        assert rows[0].relative_storage_path != rows[1].relative_storage_path
    assert len(stored_files(settings)) == 2


@pytest.mark.parametrize("role", ["club_management", "player"])
def test_readonly_roles_cannot_upload_or_replace(client, domain, role, clip):
    _, headers = role_account(client, domain, role)
    for method in ("POST", "PUT"):
        assert upload(client, domain, headers, clip, method=method).status_code == 403


def test_analyst_upload_and_manager_metadata_access(client, domain, clip):
    _, analyst = role_account(client, domain, "analyst")
    result = upload(client, domain, analyst, clip)
    assert result.status_code == 201
    _, manager = role_account(client, domain, "club_management")
    assert (
        client.get(
            f"/api/matches/{result.json()['match_id']}/video", headers=manager
        ).status_code
        == 200
    )


def test_unassigned_and_anonymous_rejected_before_body_parsing(
    client, domain, coach_headers
):
    match = domain["matches"][1]["id"]
    for suffix in ("video", "video/file"):
        assert (
            client.get(
                f"/api/matches/{match}/{suffix}", headers=coach_headers
            ).status_code
            == 404
        )
    for method in ("POST", "PUT"):
        path = f"/api/matches/{match}/video"
        assert (
            client.request(
                method, path, headers=coach_headers, content=b"bad"
            ).status_code
            == 404
        )
        assert client.request(method, path, content=b"bad").status_code == 401


def test_publication_failure_cleans_file_and_preserves_previous(
    client, domain, coach_headers, clip, settings, monkeypatch
):
    initial = upload(client, domain, coach_headers, clip).json()
    from sqlalchemy.exc import IntegrityError

    def fail_flush(*args, **kwargs):
        raise IntegrityError("fixture failure", {}, Exception("internal fixture"))

    monkeypatch.setattr(Session, "flush", fail_flush)
    response = upload(
        client, domain, coach_headers, clip + b"\x00\x00\x00\x08free", method="PUT"
    )
    assert response.status_code == 409
    assert len(stored_files(settings)) == 1
    monkeypatch.undo()
    assert (
        client.get(
            f"/api/matches/{initial['match_id']}/video", headers=coach_headers
        ).json()["id"]
        == initial["id"]
    )


def test_stale_source_check_and_bounded_service_reads(
    client, domain, coach, coach_headers, clip, session, settings
):
    initial = upload(client, domain, coach_headers, clip).json()

    class BoundedReader(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= upload_service.CHUNK_SIZE
            return super().read(size)

    with pytest.raises(DomainError) as error:
        upload_service.receive_video(
            session,
            coach,
            initial["match_id"],
            BoundedReader(clip),
            "a.mp4",
            "video/mp4",
            settings,
            replace=True,
            expected_video_id=99999,
        )
    assert error.value.status_code == 409
    assert len(stored_files(settings)) == 1


@pytest.mark.parametrize(
    "change,status", [("job", 409), ("account", 401), ("membership", 404)]
)
def test_replacement_rechecks_access_and_jobs_after_inspection(
    client,
    domain,
    coach,
    coach_headers,
    admin_headers,
    clip,
    settings,
    engine,
    monkeypatch,
    change,
    status,
):
    initial = upload(client, domain, coach_headers, clip).json()
    inspect = upload_service.inspect_video
    coach_id = coach.id

    def inspect_then_change_state(path, config):
        metadata = inspect(path, config)
        # Simulate another request during the slow inspection, using its own DB session.
        with Session(engine) as other:
            if change == "job":
                other.add(
                    ProcessingJob(
                        match_id=initial["match_id"],
                        video_id=initial["id"],
                        created_by_user_id=coach_id,
                        job_type="video_preparation",
                        status="queued",
                        progress_percent=0,
                        current_stage="queued",
                    )
                )
            elif change == "account":
                other.execute(
                    update(User).where(User.id == coach_id).values(is_active=False)
                )
            else:
                other.execute(
                    delete(ClubMembership).where(ClubMembership.user_id == coach_id)
                )
            other.commit()
        return metadata

    monkeypatch.setattr(upload_service, "inspect_video", inspect_then_change_state)
    response = upload(
        client, domain, coach_headers, clip + b"\x00\x00\x00\x08free", method="PUT"
    )
    assert response.status_code == status, response.text
    assert len(stored_files(settings)) == 1
    assert (
        client.get(
            f"/api/matches/{initial['match_id']}/video", headers=admin_headers
        ).json()["id"]
        == initial["id"]
    )


def test_concurrent_replacements_publish_only_one_new_source(
    client, domain, coach, coach_headers, clip, settings, engine, monkeypatch
):
    initial = upload(client, domain, coach_headers, clip).json()
    coach_id = coach.id
    barrier = Barrier(2, timeout=15)
    inspect = upload_service.inspect_video

    def inspect_together(path, config):
        metadata = inspect(path, config)
        barrier.wait()
        return metadata

    def replace_video(index):
        with Session(engine) as own_session:
            user = own_session.get(User, coach_id)
            try:
                video = upload_service.receive_video(
                    own_session,
                    user,
                    initial["match_id"],
                    io.BytesIO(clip + b"\x00\x00\x00\x08free" * index),
                    f"replacement-{index}.mp4",
                    "video/mp4",
                    settings,
                    replace=True,
                    expected_video_id=initial["id"],
                )
                return video.id
            except DomainError as error:
                assert error.status_code == 409
                return None

    monkeypatch.setattr(upload_service, "inspect_video", inspect_together)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(replace_video, (1, 2)))
    assert sum(value is not None for value in results) == 1
    with Session(engine) as session:
        videos = session.scalars(select(MatchVideo)).all()
        assert len(videos) == 2
        assert sum(video.is_active for video in videos) == 1
        assert next(video.id for video in videos if video.is_active) in results
    assert len(stored_files(settings)) == 2
