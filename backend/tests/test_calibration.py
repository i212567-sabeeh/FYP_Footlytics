"""Backend calibration with the existing small synthetic upload fixture."""

import subprocess
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
import test_football
import test_videos
from conftest import migration_config
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.models.calibration import PitchCalibration
from app.services import calibration_service, frame_service

domain = test_football.domain
clip = test_videos.clip


@pytest.fixture
def source(client, domain, coach_headers, clip):
    response = test_videos.upload(client, domain, coach_headers, clip)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def payload(source):
    return {
        "video_id": source["id"],
        "source_timestamp_seconds": 0.3,
        "image_points": [
            {"x": x, "y": y} for x, y in [(0, 0), (63, 0), (63, 47), (0, 47)]
        ],
        "pitch_points": [
            {"x": x, "y": y} for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]
        ],
    }


def endpoint(source):
    return f"/api/matches/{source['match_id']}/calibration"


def test_create_read_update_and_no_duplicate_calibration(
    client, source, payload, coach_headers, engine
):
    url = endpoint(source)
    assert client.get(url, headers=coach_headers).json() is None
    assert client.put(url, headers=coach_headers, json=payload).status_code == 404
    response = client.post(url, headers=coach_headers, json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert (
        saved["image_width"],
        saved["image_height"],
        saved["source_frame_number"],
    ) == (64, 48, 3)
    assert saved["source_timestamp_seconds"] == pytest.approx(0.3)
    assert saved["reprojection_error"] < 1e-5
    assert saved["created_at"].endswith("Z")
    assert not {"relative_storage_path", "stored_filename"}.intersection(saved)
    assert client.get(url, headers=coach_headers).json() == saved
    assert client.post(url, headers=coach_headers, json=payload).status_code == 409
    changed = {**payload, "source_timestamp_seconds": 0}
    response = client.put(url, headers=coach_headers, json=changed)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == saved["id"] and updated["source_frame_number"] == 0
    assert updated["created_at"] == saved["created_at"]
    assert updated["updated_at"] > saved["updated_at"]
    with Session(engine) as session:
        assert len(session.scalars(select(PitchCalibration)).all()) == 1


@pytest.mark.parametrize("timestamp,number", [(None, 0), (0.3, 3)])
def test_real_first_and_later_frame_jpeg(
    client, source, coach_headers, timestamp, number
):
    params = {} if timestamp is None else {"timestamp_seconds": timestamp}
    response = client.get(
        endpoint(source) + "/frame",
        headers={**coach_headers, "Origin": "http://localhost:5173"},
        params=params,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert int(response.headers["x-video-id"]) == source["id"]
    assert int(response.headers["x-frame-number"]) == number
    assert float(response.headers["x-frame-timestamp-seconds"]) == pytest.approx(
        number / 10
    )
    assert "X-Video-Id" in response.headers["access-control-expose-headers"]
    frame = cv2.imdecode(
        np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    assert frame.shape == (48, 64, 3)
    assert float(frame.mean()) == pytest.approx(number * 25, abs=5)


@pytest.mark.parametrize("timestamp", ["-1", "nan", "inf", "0.6", "100", "bad"])
def test_invalid_frame_timestamp_rejected(client, source, coach_headers, timestamp):
    assert (
        client.get(
            endpoint(source) + "/frame",
            headers=coach_headers,
            params={"timestamp_seconds": timestamp},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "fault",
    [
        "few",
        "mismatch",
        "duplicate",
        "collinear",
        "image_bounds",
        "pitch_bounds",
        "nan",
        "wrong_video",
    ],
)
def test_invalid_calibration_does_not_create_record(
    client, source, payload, coach_headers, fault
):
    if fault == "few":
        payload["image_points"] = payload["image_points"][:3]
        payload["pitch_points"] = payload["pitch_points"][:3]
    elif fault == "mismatch":
        payload["pitch_points"].append({"x": 30, "y": 30})
    elif fault == "duplicate":
        payload["image_points"][1] = payload["image_points"][0]
    elif fault == "collinear":
        payload["image_points"] = [{"x": i, "y": i} for i in range(4)]
    elif fault == "image_bounds":
        payload["image_points"][0]["x"] = 64
    elif fault == "pitch_bounds":
        payload["pitch_points"][1]["x"] = 106
    elif fault == "nan":
        payload["pitch_points"][1]["x"] = "NaN"
    else:
        payload["video_id"] += 999
    response = client.post(endpoint(source), headers=coach_headers, json=payload)
    assert response.status_code == (409 if fault == "wrong_video" else 422), (
        response.text
    )
    assert client.get(endpoint(source), headers=coach_headers).json() is None


def test_no_video_and_archived_match_rejected(
    client, domain, coach_headers, payload, source
):
    url = endpoint(source)
    other = domain["post"](
        "matches",
        {
            "club_id": domain["clubs"][0]["id"],
            "title": "No video",
            "team_a_id": domain["teams"][0]["id"],
            "team_b_id": domain["teams"][1]["id"],
            "match_format": "5v5",
            "match_date": "2026-09-01T12:00:00Z",
            "pitch_length_metres": 40,
            "pitch_width_metres": 20,
        },
    )
    empty = f"/api/matches/{other['id']}/calibration"
    assert client.post(empty, headers=coach_headers, json=payload).status_code == 409
    assert client.get(empty + "/frame", headers=coach_headers).status_code == 409
    client.patch(
        f"/api/matches/{source['match_id']}",
        headers=coach_headers,
        json={"is_archived": True},
    )
    assert client.post(url, headers=coach_headers, json=payload).status_code == 409


def test_video_replacement_hides_stale_calibration_and_rejects_old_source(
    client, domain, source, payload, coach_headers, clip, engine
):
    url = endpoint(source)
    saved = client.post(url, headers=coach_headers, json=payload)
    assert saved.status_code == 201
    replacement = test_videos.upload(
        client, domain, coach_headers, clip + b"\x00\x00\x00\x08free", method="PUT"
    )
    assert replacement.status_code == 200
    assert client.get(url, headers=coach_headers).json() is None
    assert client.post(url, headers=coach_headers, json=payload).status_code == 409
    payload["video_id"] = replacement.json()["id"]
    assert client.post(url, headers=coach_headers, json=payload).status_code == 201
    with Session(engine) as session:
        assert len(session.scalars(select(PitchCalibration)).all()) == 2


def test_match_dimensions_used_and_changed_dimensions_make_calibration_stale(
    client, source, payload, coach_headers
):
    url = endpoint(source)
    client.patch(
        f"/api/matches/{source['match_id']}",
        headers=coach_headers,
        json={
            "pitch_length_metres": 40,
            "pitch_width_metres": 20,
            "match_format": "5v5",
        },
    )
    assert client.post(url, headers=coach_headers, json=payload).status_code == 422
    payload["pitch_points"] = [
        {"x": x, "y": y} for x, y in [(0, 0), (40, 0), (40, 20), (0, 20)]
    ]
    response = client.post(url, headers=coach_headers, json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["pitch_length_metres"] == 40
    client.patch(
        f"/api/matches/{source['match_id']}",
        headers=coach_headers,
        json={"pitch_length_metres": 42},
    )
    assert client.get(url, headers=coach_headers).json() is None
    payload["pitch_points"][1]["x"] = payload["pitch_points"][2]["x"] = 42
    assert client.put(url, headers=coach_headers, json=payload).status_code == 200


@pytest.mark.parametrize(
    "role,expected", [("analyst", 201), ("club_management", 403), ("player", 403)]
)
def test_calibration_roles(
    client, domain, source, payload, admin_headers, role, expected
):
    _, headers = test_football.role_account(client, domain, role)
    url = endpoint(source)
    assert client.post(url, headers=headers, json=payload).status_code == expected
    if role == "club_management":
        assert client.get(url, headers=headers).status_code == 200
        assert client.get(url + "/frame", headers=headers).status_code == 200
    assert client.put(url, headers=headers, json=payload).status_code == (
        200 if role == "analyst" else 403
    )
    assert client.get(url, headers=admin_headers).status_code == 200


def test_admin_global_and_cross_club_and_anonymous_denial(
    client, domain, source, payload, coach_headers, admin_headers, clip
):
    # The existing coach belongs only to North; Admin uploads/calibrates South.
    foreign_id = domain["matches"][1]["id"]
    uploaded = client.post(
        f"/api/matches/{foreign_id}/video",
        headers=admin_headers,
        files={"file": ("fixture.mp4", clip, "video/mp4")},
    )
    assert uploaded.status_code == 201
    payload["video_id"] = uploaded.json()["id"]
    foreign_url = f"/api/matches/{foreign_id}/calibration"
    for method, url in [
        ("GET", foreign_url),
        ("GET", foreign_url + "/frame"),
        ("POST", foreign_url),
        ("PUT", foreign_url),
    ]:
        options = {"json": payload} if method in {"POST", "PUT"} else {}
        assert (
            client.request(method, url, headers=coach_headers, **options).status_code
            == 404
        )
        assert client.request(method, url, **options).status_code == 401
    assert (
        client.post(foreign_url, headers=admin_headers, json=payload).status_code == 201
    )


def test_failed_update_preserves_calibration_and_out_of_pitch_transform_rejected(
    client, source, payload, coach_headers, monkeypatch
):
    url = endpoint(source)
    saved = client.post(url, headers=coach_headers, json=payload).json()
    monkeypatch.setattr(
        calibration_service,
        "compute_homography",
        lambda *args: np.array([[1, 0, -10], [0, 1, 0], [0, 0, 1]]),
    )
    assert client.put(url, headers=coach_headers, json=payload).status_code == 422
    assert client.get(url, headers=coach_headers).json() == saved


def test_frame_decoder_timeout_is_safe(client, source, coach_headers, monkeypatch):
    monkeypatch.setattr(
        frame_service.subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired("/private/decoder", 1)),
    )
    response = client.get(endpoint(source) + "/frame", headers=coach_headers)
    assert response.status_code == 422
    assert "private" not in response.text and "timed out" in response.text


def test_phase4_upgrade_preserves_video_jobs_and_domain(engine, source):
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0003_match_videos_processing_jobs")
        names = inspect(connection).get_table_names()
        before = {
            name: connection.execute(text(f"SELECT * FROM {name}")).all()
            for name in names
            if name != "alembic_version"
        }
        command.upgrade(config, "head")
        for name, rows in before.items():
            assert connection.execute(text(f"SELECT * FROM {name}")).all() == rows
        command.check(config)
