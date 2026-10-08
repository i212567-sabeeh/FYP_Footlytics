"""Saved-input tactics worker, assignment guards, API reload and bundle safety."""

import json
from unittest.mock import Mock

import pytest
import test_jobs
import test_player_analytics_jobs as previous
from conftest import TEST_PASSWORD, migration_config
from rq.serializers import JSONSerializer
from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from test_player_analytics import point

from alembic import command
from app.auth.tokens import create_access_token
from app.database.base import utc_now
from app.database.session import create_session_factory
from app.models.calibration import PitchCalibration
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.services.analytics_artifacts import read_rows
from app.services.coordinate_inputs import current_mapping_inputs
from app.services.domain_common import DomainError
from app.services.result_inputs import current_result
from app.services.tactics_artifacts import MODELS, TacticsArtifacts
from app.services.team_assignment_service import tracking_version
from app.services.tracking_inputs import current_detection, file_version
from app.workers import player_analytics
from app.workers import team_analytics as worker
from app.workers.queue import RQJobQueue, get_job_queue

domain = previous.domain
source_video = previous.source_video
calibrated = previous.calibrated
detections = previous.detections
tracks = previous.tracks
coordinates = previous.coordinates
upstream_queue = previous.upstream_queue
trajectory_queue = previous.trajectory_queue
analytics_queue = previous.queue


class RecordingQueue(previous.RecordingQueue):
    def enqueue_team_tactical_analytics(self, job_id, attempt, rq_job_id):
        self.enqueue_player_analytics(job_id, attempt, rq_job_id)


@pytest.fixture
def queue(client, settings, monkeypatch, analytics_queue):
    instance = RecordingQueue()
    client.app.dependency_overrides[get_job_queue] = lambda: instance
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(
        player_analytics,
        "calculate_players",
        Mock(side_effect=AssertionError("Phase 11 rerun")),
    )
    return instance


@pytest.fixture
def tactical_inputs(
    request, coordinates, tracks, detections, source_video, settings, session
):
    variant = getattr(request, "param", "normal")
    points = []
    for frame in (0, 1, 3):
        positions = [(2, 2), (6, 2), (2, 5), (12, 10), (16, 10), (12, 13), (20, 18)]
        for track, (x, y) in zip((1, 2, 3, 4, 5, 6, 9), positions, strict=True):
            if frame == 1:
                x, y = (x + 1, y) if track <= 3 else (x, y + 1)
            if frame == 3 and 4 <= track <= 6:
                x += 1
            if (frame == 3 and track == 3) or variant == "rejected":
                x = None
            points.append(
                point(
                    frame / 10,
                    x,
                    y,
                    track=track,
                    frame=frame,
                    segment=2 if frame == 3 else 1,
                )
            )
    if variant == "empty":
        points = []
    rows = []
    for p in points:
        x, y = p.clean if p.clean is not None else (-1, 0)
        px, py = (x + 10) * 2, y * 2
        rows.append(
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
    n = len(points)
    unique = len({p.track_id for p in points})
    rejected = sum(p.clean is None for p in points)
    previous.rewrite_csv(
        settings.storage_dir / detections.artifact_relative_path,
        previous.DETECTION_COLUMNS,
        rows,
    )
    detections.detection_summary = {
        **detections.detection_summary,
        "total_detections": n,
        "average_detections_per_processed_frame": n / 4,
    }
    session.commit()
    match = session.get(Match, coordinates.match_id)
    _, tracks.detection_snapshot = current_detection(
        session, match, source_video[0], tracks.calibration_snapshot, settings
    )
    previous.rewrite_csv(
        settings.storage_dir / tracks.artifact_relative_path,
        previous.TRACK_COLUMNS,
        rows,
    )
    tracks.tracking_summary = {
        **tracks.tracking_summary,
        "total_detections": n,
        "total_track_rows": n,
        "unique_tracks": unique,
    }
    session.commit()
    inputs = current_mapping_inputs(session, match, settings)
    coordinates.tracking_snapshot, coordinates.calibration_snapshot = (
        inputs.source.version,
        inputs.calibration,
    )
    path = settings.storage_dir / coordinates.artifact_relative_path
    previous.rewrite_csv(path, previous.COORDINATE_COLUMNS, rows)
    coordinates.coordinate_summary = {
        **coordinates.coordinate_summary,
        "total_rows": n,
        "valid_mapped_rows": n,
        "unique_tracks": unique,
        "inside_pitch_rows": n - rejected,
        "outside_pitch_rows": rejected,
        "first_frame": 0 if n else None,
        "last_frame": 3 if n else None,
        "artifact_version": file_version(path),
    }
    session.commit()
    points.sort(key=lambda p: (p.track_id, p.timestamp, p.frame))
    trajectories = previous.publish_trajectories(session, settings, coordinates, points)
    # Build the assignment digest from persisted SQL types, like the real worker.
    with create_session_factory(session.bind)() as persisted:
        version = tracking_version(
            current_result(
                persisted, persisted.get(Match, match.id), "tracking", settings
            ).version
        )
    for track in sorted({p.track_id for p in points}):
        automatic = (
            "team_a"
            if track <= 3 or track == 6
            else "team_b"
            if track <= 5
            else "unknown"
        )
        session.add(
            TrackTeamAssignment(
                match_id=match.id,
                tracking_job_id=tracks.id,
                tracking_version=version,
                track_id=track,
                automatic_team=automatic,
                automatic_confidence=0.9,
                manual_team="team_b" if track == 6 else None,
            )
        )
    session.commit()
    return trajectories


def enqueue(client, match_id, headers):
    response = client.post(
        f"/api/matches/{match_id}/jobs/team-tactical-analytics", headers=headers
    )
    assert response.status_code == 202, response.text
    return response.json()


def result(client, match_id, headers, suffix=""):
    return client.get(
        f"/api/matches/{match_id}/team-analytics{suffix}", headers=headers
    )


def bundles(settings):
    return list((settings.storage_dir / "team_analytics").rglob("attempt-*"))


def change_team(client, match_id, headers, team="team_b", track=1):
    return client.patch(
        f"/api/matches/{match_id}/tracks/{track}/team",
        headers=headers,
        json={"team": team},
    )


def test_synthetic_smoke_bundle_progress_effective_teams_and_api_reload(
    client,
    tactical_inputs,
    settings,
    engine,
    coach_headers,
    queue,
    monkeypatch,
    record_property,
):
    match_id = tactical_inputs.match_id
    original = (
        settings.storage_dir / tactical_inputs.artifact_relative_path
    ).read_bytes()
    job = enqueue(client, match_id, coach_headers)
    assert (
        job["tactics_summary"] is None and job["job_type"] == "team_tactical_analytics"
    )
    assert queue.calls[0][:2] == (job["id"], 0)
    assert result(client, match_id, coach_headers).status_code == 409
    progress = Mock(wraps=worker._running)
    monkeypatch.setattr(worker, "_running", progress)
    worker.analyze_teams(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert stored.status == "completed_with_warnings" and stored.progress_percent == 100
    path = settings.storage_dir / stored.artifact_relative_path
    assert {p.name for p in path.iterdir()} == {f"{name}.csv" for name in MODELS}
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert (
        stored.tactics_summary["unknown_rows"] == 3
        and stored.tactics_summary["assigned_rows"] == 17
    )
    percentages = [
        c.kwargs["progress_percent"]
        for c in progress.call_args_list
        if "progress_percent" in c.kwargs
    ]
    assert percentages == [40, 60, 81, 99, 100]
    response = result(client, match_id, coach_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["aggregation"] == "per_valid_snapshot"
    assert (
        data["summary"]["pitch_length_metres"] == 30
        and data["summary"]["pitch_width_metres"] == 20
    )
    a, b = data["teams"]
    assert (
        a["valid_snapshots"],
        a["insufficient_snapshots"],
        b["valid_snapshots"],
    ) == (2, 1, 3)
    assert a["avg_centroid_x"] == pytest.approx(23 / 6) and a["avg_centroid_y"] == 3
    assert b["avg_centroid_x"] == pytest.approx(41 / 3) and b[
        "avg_centroid_y"
    ] == pytest.approx(34 / 3)
    assert a["avg_width_metres"] == b["avg_width_metres"] == 3
    assert a["avg_depth_metres"] == b["avg_depth_metres"] == 4
    assert a["avg_pairwise_distance_metres"] == b["avg_pairwise_distance_metres"] == 4
    assert a["avg_convex_hull_area_m2"] == b["avg_convex_hull_area_m2"] == 6
    frames = {}
    for team in ("team_a", "team_b"):
        detail = result(client, match_id, coach_headers, f"/{team}")
        assert detail.json() == (a if team == "team_a" else b)
        series = result(client, match_id, coach_headers, f"/{team}/series").json()
        assert series["total"] == 3 and len(series["items"]) == 3
        frames[team] = series["items"]
        first = series["items"][0]
        assert first["visible_players"] == 3
        assert first["width_metres"] == 3 and first["depth_metres"] == 4
        assert first["compactness_radius_metres"] == pytest.approx(
            (5 + 73**0.5 + 52**0.5) / 9
        )
        assert first["centroid_distance_to_opponent_metres"] == pytest.approx(164**0.5)
    assert frames["team_a"][2]["visible_players"] == 2
    assert frames["team_a"][2]["width_metres"] is None
    page = result(
        client, match_id, coach_headers, "/team_a/series?offset=1&limit=1"
    ).json()
    assert page["items"] == [frames["team_a"][1]] and page["total"] == 3
    assert not result(
        client, match_id, coach_headers, "/team_a/series?offset=3"
    ).json()["items"]
    for private in ("artifact", "snapshot", "relative_path", str(settings.storage_dir)):
        # "snapshot" is a public metric/method word; paths/manifests are private.
        if private != "snapshot":
            assert private not in response.text.replace(
                '"artifact_format":"csv_bundle"', ""
            )
    assert (
        settings.storage_dir / tactical_inputs.artifact_relative_path
    ).read_bytes() == original
    artifacts = {
        name: [r.model_dump() for r in read_rows(path / f"{name}.csv", name, MODELS)]
        for name in MODELS
    }
    assert len(artifacts["team_tactics_frames"]) == 6
    smoke = {"api": data, "frames": frames, "artifacts": artifacts}
    json.dumps(smoke, allow_nan=False)
    record_property("team_analytics_smoke", smoke)
    worker.analyze_teams(job["id"], 0)  # duplicate delivery cannot overwrite
    assert len(bundles(settings)) == 1


def test_effective_assignment_changes_invalidate_but_masked_automatic_changes_do_not(
    client, tactical_inputs, coach_headers, queue, session
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(job["id"], 0)
    row = session.scalar(
        select(TrackTeamAssignment).where(TrackTeamAssignment.track_id == 6)
    )
    row.automatic_team, row.automatic_confidence = "unknown", 0.2
    session.commit()
    assert result(client, tactical_inputs.match_id, coach_headers).status_code == 200
    assert (
        change_team(client, tactical_inputs.match_id, coach_headers).status_code == 200
    )
    for suffix in ("", "/team_a", "/team_b/series"):
        response = result(client, tactical_inputs.match_id, coach_headers, suffix)
        assert response.status_code == 409 and "stale" in response.text


def test_player_analytics_jobs_and_metadata_do_not_invalidate_tactics(
    client, tactical_inputs, coach_headers, queue, session
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(job["id"], 0)
    previous_result = result(client, tactical_inputs.match_id, coach_headers).json()
    # A Phase 11 rerun may replace its entire metadata; Phase 12 has no dependency.
    analytics = ProcessingJob(
        match_id=tactical_inputs.match_id,
        video_id=tactical_inputs.video_id,
        job_type="player_analytics",
        status="completed",
        progress_percent=100,
        current_stage="completed",
        created_by_user_id=tactical_inputs.created_by_user_id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        analytics_summary={"fixture": "first"},
    )
    session.add(analytics)
    session.commit()
    analytics.analytics_summary, analytics.updated_at = (
        {"fixture": "replacement"},
        utc_now(),
    )
    session.commit()
    assert (
        result(client, tactical_inputs.match_id, coach_headers).json()
        == previous_result
    )


@pytest.mark.parametrize(
    "fault",
    [
        "video",
        "calibration",
        "tracking",
        "coordinates",
        "trajectory",
        "replacement_trajectory",
        "assignment",
        "file",
    ],
)
@pytest.mark.parametrize("when", ["during", "after"])
def test_upstream_and_assignment_changes_never_publish_or_serve_stale_results(
    client,
    tactical_inputs,
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
    when,
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    changed = False
    real_write = TacticsArtifacts.write

    def mutate():
        if fault == "assignment":
            assert (
                change_team(client, tactical_inputs.match_id, coach_headers).status_code
                == 200
            )
            return
        with create_session_factory(engine)() as session:
            if fault == "replacement_trajectory":
                old = session.get(ProcessingJob, tactical_inputs.id)
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
            elif fault == "video":
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
                path = settings.storage_dir / tactical_inputs.artifact_relative_path
                path.write_bytes(path.read_bytes() + b"\n")
            else:
                identity = {
                    "tracking": tracks.id,
                    "coordinates": coordinates.id,
                    "trajectory": tactical_inputs.id,
                }[fault]
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == identity)
                    .values(updated_at=utc_now())
                )
            session.commit()

    def write(artifact, name, row):
        nonlocal changed
        real_write(artifact, name, row)
        if not changed:
            changed = True
            mutate()

    if when == "during":
        monkeypatch.setattr(TacticsArtifacts, "write", write)
        with pytest.raises(DomainError):
            worker.analyze_teams(job["id"], 0)
        stored = test_jobs.persisted_job(engine, job["id"])
        assert stored.status == "failed" and stored.artifact_relative_path is None
        assert stored.tactics_summary is None and not bundles(settings)
        assert str(settings.storage_dir) not in stored.error_message
    else:
        worker.analyze_teams(job["id"], 0)
        mutate()
        assert (
            result(client, tactical_inputs.match_id, coach_headers).status_code == 409
        )


@pytest.mark.parametrize(
    "fault", ["frames", "summary", "before_publish", "publish", "commit"]
)
def test_failures_and_retries_preserve_previous_complete_bundle(
    client, tactical_inputs, settings, engine, coach_headers, queue, monkeypatch, fault
):
    first = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(first["id"], 0)
    old = test_jobs.persisted_job(engine, first["id"])
    old_path = settings.storage_dir / old.artifact_relative_path
    original = {p.name: p.read_bytes() for p in old_path.iterdir()}
    second = enqueue(client, tactical_inputs.match_id, coach_headers)
    assert (
        result(client, tactical_inputs.match_id, coach_headers).json()["job_id"]
        == first["id"]
    )
    real_write, real_publish, real_running = (
        TacticsArtifacts.write,
        TacticsArtifacts.publish,
        worker._running,
    )

    def write(artifact, name, row):
        real_write(artifact, name, row)
        if name == (
            "team_tactics_frames" if fault == "frames" else "team_tactics_summary"
        ):
            raise OSError("/private/team-analytics.csv")

    def publish(artifact):
        if fault == "publish":
            real_publish(artifact)
        raise OSError("/private/team-analytics.csv")

    def running(session, job_id, attempt, **values):
        if values.get("status") in ("completed", "completed_with_warnings"):
            raise OSError("/private/team-analytics.csv")
        return real_running(session, job_id, attempt, **values)

    for attempt in (0, 1):
        with monkeypatch.context() as patch:
            if fault in ("frames", "summary"):
                patch.setattr(TacticsArtifacts, "write", write)
            elif fault == "commit":
                patch.setattr(worker, "_running", running)
            else:
                patch.setattr(TacticsArtifacts, "publish", publish)
            with pytest.raises(OSError):
                worker.analyze_teams(second["id"], attempt)
        failed = test_jobs.persisted_job(engine, second["id"])
        assert failed.status == "failed" and "/private" not in failed.error_message
        assert failed.artifact_relative_path is None and failed.tactics_summary is None
        assert bundles(settings) == [old_path]
        assert original == {p.name: p.read_bytes() for p in old_path.iterdir()}
        assert (
            result(client, tactical_inputs.match_id, coach_headers).json()["job_id"]
            == first["id"]
        )
        assert (
            client.post(
                f"/api/jobs/{second['id']}/retry", headers=coach_headers
            ).status_code
            == 202
        )
        worker.analyze_teams(second["id"], attempt)
        assert test_jobs.persisted_job(engine, second["id"]).status == "queued"
    worker.analyze_teams(second["id"], 2)
    assert (
        "/attempt-2-"
        in test_jobs.persisted_job(engine, second["id"]).artifact_relative_path
    )
    assert (
        result(client, tactical_inputs.match_id, coach_headers).json()["job_id"]
        == second["id"]
    )
    assert len(bundles(settings)) == 2


def test_atomic_bundle_rename_and_post_publication_guard(
    client, tactical_inputs, settings, engine, coach_headers, queue, monkeypatch
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    real_publish = TacticsArtifacts.publish

    def publish(artifact):
        assert not artifact.path.exists()
        assert {p.name for p in artifact.temporary.iterdir()} == {
            f"{name}.csv" for name in MODELS
        }
        relative = real_publish(artifact)
        assert not artifact.temporary.exists()
        assert {p.name for p in artifact.path.iterdir()} == {
            f"{name}.csv" for name in MODELS
        }
        path = settings.storage_dir / tactical_inputs.artifact_relative_path
        path.write_bytes(path.read_bytes() + b"\n")
        return relative

    monkeypatch.setattr(TacticsArtifacts, "publish", publish)
    with pytest.raises(DomainError):
        worker.analyze_teams(job["id"], 0)
    assert (
        not bundles(settings)
        and test_jobs.persisted_job(engine, job["id"]).status == "failed"
    )


@pytest.mark.parametrize(
    "fault",
    ["team_tactics_frames", "team_tactics_summary", "manifest", "path", "summary"],
)
def test_damaged_bundles_are_not_current(
    client, tactical_inputs, settings, session, coach_headers, queue, fault
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(job["id"], 0)
    stored = session.get(ProcessingJob, job["id"])
    if fault in MODELS:
        (settings.storage_dir / stored.artifact_relative_path / f"{fault}.csv").unlink()
    elif fault == "path":
        stored.artifact_relative_path = "../../private"
    elif fault == "manifest":
        stored.tactics_summary = {**stored.tactics_summary, "artifact_versions": {}}
    else:
        stored.tactics_summary = {**stored.tactics_summary, "usable_rows": 999}
    session.commit()
    for suffix in ("", "/team_a", "/team_b/series"):
        response = result(client, tactical_inputs.match_id, coach_headers, suffix)
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
    client, tactical_inputs, coach_headers, queue, domain, settings, role, read, write
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(job["id"], 0)
    account = domain["post"](
        "users",
        {
            "email": f"tactics-{role}@example.com",
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
    for suffix in ("", "/team_a", "/team_b/series"):
        assert (
            result(client, tactical_inputs.match_id, headers, suffix).status_code
            == read
        )
    assert (
        client.post(
            f"/api/matches/{tactical_inputs.match_id}/jobs/team-tactical-analytics",
            headers=headers,
        ).status_code
        == write
    )


def test_cross_club_and_anonymous_denied(client, domain, coach_headers, queue):
    match_id = domain["matches"][1]["id"]
    for headers, status in ((coach_headers, 404), ({}, 401)):
        for suffix in ("", "/team_a", "/team_b/series"):
            assert result(client, match_id, headers, suffix).status_code == status
        assert (
            client.post(
                f"/api/matches/{match_id}/jobs/team-tactical-analytics", headers=headers
            ).status_code
            == status
        )
    assert not queue.calls


@pytest.mark.parametrize(
    "suffix",
    ["/unknown", "/red/series", "/team_a/series?limit=101", "/team_a/series?offset=-1"],
)
def test_invalid_team_and_pagination(client, domain, coach_headers, suffix):
    assert (
        result(client, domain["matches"][0]["id"], coach_headers, suffix).status_code
        == 422
    )


@pytest.mark.parametrize(
    "fault", ["trajectories", "assignments", "stale_assignments", "missing_file"]
)
def test_missing_and_stale_inputs_do_not_enqueue(
    client, tactical_inputs, settings, session, coach_headers, queue, fault
):
    if fault == "trajectories":
        tactical_inputs.status = "failed"
    elif fault == "missing_file":
        (settings.storage_dir / tactical_inputs.artifact_relative_path).unlink()
    else:
        for row in session.scalars(select(TrackTeamAssignment)):
            if fault == "assignments":
                session.delete(row)
            else:
                row.tracking_version = "f" * 64
    session.commit()
    response = client.post(
        f"/api/matches/{tactical_inputs.match_id}/jobs/team-tactical-analytics",
        headers=coach_headers,
    )
    assert response.status_code == 409 and not queue.calls


@pytest.mark.parametrize("tactical_inputs", ["empty", "rejected"], indirect=True)
def test_empty_and_rejected_results_are_explicit(
    client, tactical_inputs, coach_headers, queue
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(job["id"], 0)
    response = result(client, tactical_inputs.match_id, coach_headers)
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["observed_frames"] == 0
    assert all(
        t["valid_snapshots"] == 0 and t["avg_width_metres"] is None
        for t in response.json()["teams"]
    )


@pytest.mark.parametrize(
    "mode", ["all_unknown", "only_a", "threshold", "missing_track_assignment"]
)
def test_insufficient_team_data_is_not_fabricated(
    client, tactical_inputs, session, settings, coach_headers, queue, mode
):
    if mode == "threshold":
        settings.tactics_min_players_per_team = 4
    elif mode == "missing_track_assignment":
        row = session.scalar(
            select(TrackTeamAssignment).where(TrackTeamAssignment.track_id == 6)
        )
        session.delete(row)
        session.commit()
    else:
        session.execute(
            update(TrackTeamAssignment).values(
                manual_team="unknown" if mode == "all_unknown" else "team_a"
            )
        )
        session.commit()
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    worker.analyze_teams(job["id"], 0)
    data = result(client, tactical_inputs.match_id, coach_headers).json()
    assert data["teams"][1]["avg_width_metres"] is None
    if mode not in ("only_a", "missing_track_assignment"):
        assert data["teams"][0]["avg_width_metres"] is None
    json.dumps(data, allow_nan=False)


def test_queue_failure_duplicate_active_and_ids_only(
    client, tactical_inputs, settings, engine, coach_headers, queue, monkeypatch
):
    first = enqueue(client, tactical_inputs.match_id, coach_headers)
    assert (
        client.post(
            f"/api/matches/{tactical_inputs.match_id}/jobs/team-tactical-analytics",
            headers=coach_headers,
        ).status_code
        == 409
    )
    test_jobs.fail_job(engine, first["id"])
    monkeypatch.setattr(
        queue,
        "enqueue_team_tactical_analytics",
        Mock(side_effect=OSError("/private/redis")),
    )
    response = client.post(f"/api/jobs/{first['id']}/retry", headers=coach_headers)
    assert response.status_code == 503 and "private" not in response.text
    assert test_jobs.persisted_job(engine, first["id"]).status == "failed"
    rq = RQJobQueue(settings)
    persist = Mock(side_effect=lambda job, *_args, **_kwargs: job)
    monkeypatch.setattr(rq.queue, "enqueue_job", persist)
    rq.enqueue_team_tactical_analytics(12, 3, "tactics-attempt")
    delivered = persist.call_args.args[0]
    assert JSONSerializer.loads(delivered.data) == [
        "app.workers.team_analytics.analyze_teams",
        None,
        [],
        {"processing_job_id": 12, "attempt": 3},
    ]
    assert delivered.timeout == settings.detection_job_timeout_seconds
    rq.close()


def test_queued_assignment_change_fails_and_retry_snapshots_current_state(
    client, tactical_inputs, engine, coach_headers, queue, settings
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    old = test_jobs.persisted_job(engine, job["id"]).assignment_snapshot
    assert (
        change_team(client, tactical_inputs.match_id, coach_headers).status_code == 200
    )
    with pytest.raises(DomainError, match="assignments changed"):
        worker.analyze_teams(job["id"], 0)
    assert not bundles(settings)
    assert (
        client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers).status_code
        == 202
    )
    assert test_jobs.persisted_job(engine, job["id"]).assignment_snapshot != old
    worker.analyze_teams(job["id"], 1)
    response = result(client, tactical_inputs.match_id, coach_headers)
    assert response.status_code == 200
    a, b = response.json()["teams"]
    assert a["valid_snapshots"] == 0 and b["valid_snapshots"] == 3


def test_superseded_attempt_cannot_publish(
    client, tactical_inputs, settings, engine, coach_headers, queue, monkeypatch
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    real_write = TacticsArtifacts.write
    changed = False

    def write(artifact, name, row):
        nonlocal changed
        real_write(artifact, name, row)
        if not changed:
            changed = True
            with create_session_factory(engine)() as session:
                session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == job["id"])
                    .values(attempt=1, status="queued")
                )
                session.commit()

    monkeypatch.setattr(TacticsArtifacts, "write", write)
    worker.analyze_teams(job["id"], 0)
    stored = test_jobs.persisted_job(engine, job["id"])
    assert (
        stored.status == "queued"
        and stored.attempt == 1
        and stored.artifact_relative_path is None
    )
    assert not bundles(settings)


def test_populated_0010_upgrade_preserves_all_results_and_overrides(
    engine, tactical_inputs, session
):
    # Add existing physical-analytics metadata before upgrading the populated DB.
    job = ProcessingJob(
        match_id=tactical_inputs.match_id,
        video_id=tactical_inputs.video_id,
        job_type="player_analytics",
        status="completed",
        progress_percent=100,
        current_stage="completed",
        created_by_user_id=tactical_inputs.created_by_user_id,
        attempt=0,
        retry_count=0,
        finished_at=utc_now(),
        trajectory_snapshot={"fixture": "provenance"},
        analytics_summary={"fixture": "retained"},
    )
    session.add(job)
    session.commit()
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0010_player_analytics")
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
        assert any(r["manual_team"] for r in before["track_team_assignments"])
        assert any(r["analytics_summary"] for r in before["processing_jobs"])
        command.upgrade(config, "head")
        for name, original in before.items():
            current = (
                connection.execute(text(f"SELECT * FROM {name} ORDER BY id"))
                .mappings()
                .all()
            )
            assert [{k: row[k] for k in original[0]} for row in current] == original
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0015_team_color_prototypes"
        )
        assert {"tactics_summary", "assignment_snapshot"} <= {
            c["name"] for c in inspect(connection).get_columns("processing_jobs")
        }
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        command.check(config)
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE track_team_assignments SET tracking_job_id = 999999")
            )


def test_downgrade_refuses_tactical_history(
    client, tactical_inputs, engine, coach_headers, queue
):
    job = enqueue(client, tactical_inputs.match_id, coach_headers)
    with (
        engine.begin() as connection,
        pytest.raises(RuntimeError, match="team tactical analytics jobs"),
    ):
        command.downgrade(migration_config(connection), "0010_player_analytics")
    # Later revisions may downgrade before the 0011 history guard rejects the
    # requested downgrade. Inspect preserved data without querying newer columns.
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(ProcessingJob.job_type).where(ProcessingJob.id == job["id"])
            )
            == "team_tactical_analytics"
        )
