"""Small saved-artifact previews with real frame decoding; no inference or tracking."""

import csv
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import test_detection_jobs
import test_football
import test_jobs
import test_tracking_jobs
from conftest import TEST_PASSWORD
from sqlalchemy import update

from app.auth.tokens import create_access_token
from app.core.jobs import JobStatus, JobType
from app.cv.detector import YoloPlayerDetector
from app.cv.tracker import ByteTrackTracker, TrackedDetection
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.football import Match
from app.models.media import ProcessingJob
from app.services import review_service
from app.services.tracking_artifacts import TrackingArtifact
from app.services.tracking_inputs import current_detection

domain = test_football.domain
source_video = test_jobs.source_video
calibrated = test_detection_jobs.calibrated
detections = test_tracking_jobs.detections


@pytest.fixture(autouse=True)
def no_cv_execution(monkeypatch):
    for cls in (YoloPlayerDetector, ByteTrackTracker):
        monkeypatch.setattr(
            cls,
            "__init__",
            Mock(side_effect=AssertionError("Review must only read saved artifacts")),
        )


@pytest.fixture
def tracks(detections, source_video, settings, session, admin):
    video = source_video[0]
    _, provenance = current_detection(
        session,
        session.get(Match, video.match_id),
        video,
        detections.calibration_snapshot,
        settings,
    )
    job = ProcessingJob(
        match_id=video.match_id,
        video_id=video.id,
        job_type=JobType.PLAYER_TRACKING,
        status=JobStatus.COMPLETED,
        progress_percent=100,
        current_stage="completed",
        created_by_user_id=admin.id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        calibration_snapshot=detections.calibration_snapshot,
        detection_snapshot=provenance,
        tracking_summary={
            "processed_frames": 4,
            "total_detections": 6,
            "total_track_rows": 6,
            "unique_tracks": 2,
            "frame_stride": 1,
            "frame_width": 64,
            "frame_height": 48,
            "detection_job_id": detections.id,
            "detection_attempt": 0,
            "tracker": "bytetrack",
            "track_high_thresh": 0.25,
            "track_low_thresh": 0.1,
            "track_match_thresh": 0.8,
            "track_buffer": 30,
            "artifact_format": "csv",
        },
    )
    session.add(job)
    session.flush()
    with TrackingArtifact(settings, video.match_id, video.id, job.id, 0) as artifact:
        for number in (0, 1, 3):
            artifact.write_tracks(
                number,
                number / 10,
                [
                    TrackedDetection(3, (10 + number, 5, 20 + number, 40), 0.9),
                    TrackedDetection(7, (40, 5, 50, 40), 0.85),
                ],
            )
        job.artifact_relative_path = artifact.publish()
        session.commit()
        artifact.keep()
    return job


def url(job, kind, action="preview"):
    return f"/api/matches/{job.match_id}/{kind}/{action}"


def test_detection_preview_uses_csv_boxes_and_exact_decoded_frame(
    client, detections, coach_headers, monkeypatch
):
    rectangle = Mock(wraps=cv2.rectangle)
    text = Mock(wraps=cv2.putText)
    monkeypatch.setattr(cv2, "rectangle", rectangle)
    monkeypatch.setattr(cv2, "putText", text)
    response = client.get(
        url(detections, "detections") + "?frame_number=3", headers=coach_headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-number"] == "3"
    assert float(response.headers["x-frame-timestamp-seconds"]) == pytest.approx(0.3)
    assert response.headers["x-job-id"] == str(detections.id)
    decoded = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (48, 64, 3)
    assert any(
        call.args[1:3] == ((13, 5), (23, 40)) for call in rectangle.call_args_list
    )
    assert [call.args[1] for call in text.call_args_list] == [
        "person 90%",
        "person 85%",
    ]
    assert (
        decoded[25, 13, 1] > decoded[25, 13, 0] + 20
    )  # Actual green box in encoded JPEG.
    summary = client.get(
        url(detections, "detections", "summary"), headers=coach_headers
    ).json()
    assert (
        summary["processed_frames"],
        summary["total_detections"],
        summary["average_detections_per_processed_frame"],
    ) == (4, 6, 1.5)
    assert not {
        "artifact_relative_path",
        "calibration_snapshot",
        "detections",
    }.intersection(summary)


def test_tracking_preview_labels_persistent_ids_and_exposes_small_summary(
    client, tracks, coach_headers, monkeypatch
):
    text = Mock(wraps=cv2.putText)
    monkeypatch.setattr(cv2, "putText", text)
    for frame in (0, 1, 3):
        response = client.get(
            url(tracks, "tracking") + f"?frame_number={frame}", headers=coach_headers
        )
        assert response.status_code == 200
        assert [call.args[1] for call in text.call_args_list[-2:]] == ["ID 3", "ID 7"]
    summary = client.get(
        url(tracks, "tracking", "summary"), headers=coach_headers
    ).json()
    assert (
        summary["unique_tracks"],
        summary["tracked_rows"],
        summary["processed_frames"],
    ) == (2, 6, 4)
    assert (summary["first_frame"], summary["last_frame"], summary["frame_stride"]) == (
        0,
        3,
        1,
    )
    assert summary["average_visible_tracks_per_frame"] == 1.5
    assert (
        "detection_snapshot" not in summary and "artifact_relative_path" not in summary
    )


def test_empty_processed_frames_render_original_without_invented_boxes(
    client, tracks, coach_headers, monkeypatch
):
    text = Mock(wraps=cv2.putText)
    monkeypatch.setattr(cv2, "putText", text)
    for kind in ("detections", "tracking"):
        response = client.get(
            url(tracks, kind) + "?frame_number=2", headers=coach_headers
        )
        assert response.status_code == 200 and response.headers["x-frame-number"] == "2"
        image = cv2.imdecode(
            np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR
        )
        assert image.std() < 3
    text.assert_not_called()


@pytest.mark.parametrize("empty", [False, True])
def test_default_selects_first_observed_frame_or_zero_for_empty_results(
    client, detections, coach_headers, settings, session, empty
):
    path = settings.storage_dir / detections.artifact_relative_path
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = [row for row in reader if not empty and row["frame_number"] != "0"]
        fields = reader.fieldnames
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    detections.detection_summary = {
        **detections.detection_summary,
        "total_detections": len(rows),
        "average_detections_per_processed_frame": len(rows) / 4,
    }
    session.commit()
    response = client.get(url(detections, "detections"), headers=coach_headers)
    assert response.status_code == 200
    assert response.headers["x-frame-number"] == ("0" if empty else "1")


def test_tracking_only_candidates_never_change_detection_review(
    client, detections, settings, session, coach_headers, monkeypatch
):
    path = settings.storage_dir / detections.artifact_relative_path
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    # Frame 0 keeps one box below YOLO_CONFIDENCE, stored only for ByteTrack.
    rows = [{**rows[0], "confidence": "0.15"}, *rows[2:]]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    detections.detection_summary = {
        **detections.detection_summary,
        "total_detections": 4,
        "low_confidence_detections": 1,
        "average_detections_per_processed_frame": 1.0,
    }
    session.commit()
    text = Mock(wraps=cv2.putText)
    monkeypatch.setattr(cv2, "putText", text)
    default = client.get(url(detections, "detections"), headers=coach_headers)
    assert default.status_code == 200
    assert default.headers["x-frame-number"] == "1"  # First reported frame.
    text.reset_mock()
    hidden = client.get(
        url(detections, "detections") + "?frame_number=0", headers=coach_headers
    )
    assert hidden.status_code == 200
    text.assert_not_called()
    # The last frame reads the whole artifact, including the candidate row.
    last = client.get(
        url(detections, "detections") + "?frame_number=3", headers=coach_headers
    )
    assert last.status_code == 200
    summary = client.get(
        url(detections, "detections", "summary"), headers=coach_headers
    ).json()
    assert (
        summary["total_detections"],
        summary["average_detections_per_processed_frame"],
    ) == (4, 1.0)


@pytest.mark.parametrize(
    "query",
    ["frame_number=-1", "frame_number=1.5", "frame_number=4", "frame_number=oops"],
)
def test_invalid_frame_selection_rejected(client, tracks, coach_headers, query):
    for kind in ("detections", "tracking"):
        assert (
            client.get(
                url(tracks, kind) + "?" + query, headers=coach_headers
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_detection",
        "missing_tracks",
        "calibration",
        "retired_video",
        "unsafe_path",
        "new_detection_attempt",
    ],
)
def test_missing_stale_and_unsafe_sources_are_not_reviewed(
    client,
    tracks,
    detections,
    calibrated,
    source_video,
    settings,
    session,
    coach_headers,
    fault,
):
    if fault == "missing_detection":
        (settings.storage_dir / detections.artifact_relative_path).unlink()
    elif fault == "missing_tracks":
        (settings.storage_dir / tracks.artifact_relative_path).unlink()
    elif fault == "calibration":
        calibrated.updated_at = utc_now()
    elif fault == "retired_video":
        source_video[0].is_active = False
    elif fault == "unsafe_path":
        tracks.artifact_relative_path = "../private.csv"
    else:
        detections.updated_at = utc_now()
    session.commit()
    for action in ("summary", "preview"):
        response = client.get(url(tracks, "tracking", action), headers=coach_headers)
        assert response.status_code == 409
        assert (
            str(settings.storage_dir) not in response.text
            and "private.csv" not in response.text
        )


def test_browser_cannot_request_a_superseded_result_version(
    client, tracks, coach_headers
):
    for kind in ("detections", "tracking"):
        assert (
            client.get(
                url(tracks, kind), params={"job_id": 99999}, headers=coach_headers
            ).status_code
            == 409
        )
        assert (
            client.get(
                url(tracks, kind),
                params={"job_updated_at": "2020-01-01T00:00:00Z"},
                headers=coach_headers,
            ).status_code
            == 409
        )


def test_result_changed_during_decode_is_rejected(
    client, tracks, calibrated, engine, coach_headers, monkeypatch
):
    extract = review_service.extract_frame
    calibration_id = calibrated.id

    def changed(*args, **kwargs):
        frame = extract(*args, **kwargs)
        with create_session_factory(engine)() as session:
            session.execute(
                update(PitchCalibration)
                .where(PitchCalibration.id == calibration_id)
                .values(updated_at=utc_now())
            )
            session.commit()
        return frame

    monkeypatch.setattr(review_service, "extract_frame", changed)
    assert client.get(url(tracks, "tracking"), headers=coach_headers).status_code == 409


@pytest.mark.parametrize(
    "role", ["admin", "coach", "analyst", "club_management", "player"]
)
def test_review_role_permissions(client, tracks, domain, settings, role):
    account = domain["post"](
        "users",
        {
            "email": f"review-{role}@example.com",
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
    for kind in ("detections", "tracking"):
        for action in ("summary", "preview"):
            assert client.get(
                url(tracks, kind, action), headers=headers
            ).status_code == (403 if role == "player" else 200)


def test_other_club_and_anonymous_review_denied(client, domain, coach_headers):
    for kind in ("detections", "tracking"):
        for action in ("summary", "preview"):
            path = f"/api/matches/{domain['matches'][1]['id']}/{kind}/{action}"
            assert client.get(path, headers=coach_headers).status_code == 404
            assert client.get(path).status_code == 401


def test_corrupt_track_boxes_are_not_drawn(client, tracks, settings, coach_headers):
    path = settings.storage_dir / tracks.artifact_relative_path
    path.write_text(
        path.read_text().replace("10,5,20,40", "10,5,10,40"), encoding="utf-8"
    )
    response = client.get(url(tracks, "tracking"), headers=coach_headers)
    assert response.status_code == 409
