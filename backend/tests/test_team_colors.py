"""Human-seeded colors use saved tracks, bounded crops and existing queued jobs."""

from collections import Counter

import pytest
import test_team_classification_jobs as existing
from sqlalchemy import select

from app.core.teams import TrackTeam
from app.cv.team_classifier import Appearance
from app.cv.team_colors import classify_seeded, fit_prototype, validate_prototypes
from app.database.session import create_session_factory
from app.models.media import ProcessingJob
from app.models.team_colors import TeamColorSet
from app.services import team_color_service as service
from app.workers import team_classification as worker

for_fixture = existing
source_video = existing.source_video
domain = existing.domain
calibrated = existing.calibrated
detections = existing.detections
tracks = existing.tracks
queue = existing.queue
frames = existing.frames


@pytest.fixture(autouse=True)
def same_frames(frames, queue, monkeypatch):
    monkeypatch.setattr(service, "extract_frame", frames)


def endpoint(tracks):
    return f"/api/matches/{tracks.match_id}/team-colors"


def selection(client, tracks, headers):
    result = client.get(endpoint(tracks), headers=headers)
    assert result.status_code == 200, result.text
    return {
        "tracking_version": result.json()["tracking_version"],
        "samples": [
            {"team": "team_a", "track_id": 3, "frame_number": 0},
            {"team": "team_b", "track_id": 7, "frame_number": 0},
        ],
    }


def save(client, tracks, headers):
    data = selection(client, tracks, headers)
    response = client.put(endpoint(tracks), headers=headers, json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_and_saved_prototypes_are_real_scoped_and_path_free(
    client, tracks, coach_headers, settings
):
    data = selection(client, tracks, coach_headers)
    preview = client.get(
        endpoint(tracks) + "/preview",
        headers=coach_headers,
        params={
            "tracking_version": data["tracking_version"],
            "track_id": 3,
            "frame_number": 0,
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["crop_data_url"].startswith("data:image/jpeg;base64,/9j/")
    assert preview.json()["usable"]
    current = save(client, tracks, coach_headers)
    assert current["current"]["classification_mode"] == "user_seeded"
    assert len(current["current"]["samples"]) == 2
    assert {p["team"] for p in current["current"]["prototypes"]} == {"team_a", "team_b"}
    assert str(settings.storage_dir) not in str(current)
    assert "relative_storage_path" not in str(current)


def test_seeded_worker_records_provenance_and_preserves_manual_override(
    client, tracks, coach_headers, engine
):
    colors = save(client, tracks, coach_headers)
    job = existing.enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(job["id"], 0)
    rows = client.get(
        f"/api/matches/{tracks.match_id}/team-assignments", headers=coach_headers
    ).json()["items"]
    assert Counter(row["automatic_team"] for row in rows) == {"team_a": 1, "team_b": 1}
    for row in rows:
        assert row["classification_mode"] == "user_seeded"
        assert (
            row["classification_provenance"]["prototype_set_id"]
            == colors["current"]["id"]
        )
        assert row["classification_provenance"]["sample_count"] == 3
        assert len(row["classification_provenance"]["sample_ids"]) == 2
        assert row["classification_provenance"]["margin"] > 0
    override = client.patch(
        f"/api/matches/{tracks.match_id}/tracks/3/team",
        headers=coach_headers,
        json={"team": "unknown"},
    )
    assert override.status_code == 200
    another = existing.enqueue(client, tracks.match_id, coach_headers)
    worker.classify_teams(another["id"], 0)
    rows = client.get(
        f"/api/matches/{tracks.match_id}/team-assignments", headers=coach_headers
    ).json()["items"]
    assert (
        rows[0]["manual_team"] == "unknown" and rows[0]["effective_team"] == "unknown"
    )
    public = client.get(f"/api/jobs/{another['id']}", headers=coach_headers).json()
    assert public["classification_summary"]["classification_mode"] == "user_seeded"
    assert "team_color_snapshot" not in public


@pytest.mark.parametrize("change", ["before", "during"])
def test_changed_prototypes_fail_safely_and_retry_captures_current(
    client, tracks, coach_headers, engine, monkeypatch, change
):
    save(client, tracks, coach_headers)
    job = existing.enqueue(client, tracks.match_id, coach_headers)
    if change == "before":
        save(client, tracks, coach_headers)
    else:
        original = worker.classify_tracking

        def classify(*args, **kwargs):
            result = original(*args, **kwargs)
            save(client, tracks, coach_headers)
            return result

        monkeypatch.setattr(worker, "classify_tracking", classify)
    with pytest.raises(Exception, match="prototypes changed"):
        worker.classify_teams(job["id"], 0)
    result = client.get(f"/api/jobs/{job['id']}", headers=coach_headers).json()
    assert (
        result["status"] == "failed" and "prototypes changed" in result["error_message"]
    )
    retry = client.post(f"/api/jobs/{job['id']}/retry", headers=coach_headers)
    assert retry.status_code == 202
    with create_session_factory(engine)() as session:
        saved = session.get(ProcessingJob, job["id"])
        latest = session.scalar(select(TeamColorSet).order_by(TeamColorSet.id.desc()))
        assert saved.team_color_snapshot["id"] == latest.id


@pytest.mark.parametrize(
    "role,write,read",
    [
        ("coach", 200, 200),
        ("analyst", 200, 200),
        ("club_management", 403, 200),
        ("player", 403, 403),
    ],
)
def test_role_access(client, tracks, domain, coach_headers, role, write, read):
    if role == "coach":
        headers = coach_headers
    else:
        _, headers = existing.test_football.role_account(client, domain, role)
    data = selection(client, tracks, coach_headers)
    assert client.get(endpoint(tracks), headers=headers).status_code == read
    assert client.put(endpoint(tracks), headers=headers, json=data).status_code == write


def test_cross_club_and_anonymous_cannot_read_or_save(
    client, tracks, coach_headers, domain, settings
):
    from app.auth.tokens import create_access_token

    user = domain["post"](
        "users",
        {
            "email": "colors-outside@example.com",
            "full_name": "Outside",
            "password": existing.TEST_PASSWORD,
            "roles": ["coach"],
        },
    )
    domain["post"](f"clubs/{domain['clubs'][1]['id']}/members", {"user_id": user["id"]})
    headers = {"Authorization": f"Bearer {create_access_token(user['id'], settings)}"}
    data = selection(client, tracks, coach_headers)
    for auth, code in ((headers, 404), ({}, 401)):
        assert client.get(endpoint(tracks), headers=auth).status_code == code
        assert client.put(endpoint(tracks), headers=auth, json=data).status_code == code
        assert client.delete(endpoint(tracks), headers=auth).status_code == code


@pytest.mark.parametrize(
    "fault",
    [
        "missing_team",
        "duplicate",
        "same_track_both_teams",
        "invalid_team",
        "stale",
        "missing_track",
    ],
)
def test_invalid_selections_are_rejected_without_saving(
    client, tracks, coach_headers, fault, engine
):
    data = selection(client, tracks, coach_headers)
    if fault == "missing_team":
        data["samples"] = data["samples"][:1]
    if fault == "duplicate":
        data["samples"].append(data["samples"][0])
    if fault == "same_track_both_teams":
        data["samples"][1].update(track_id=3, frame_number=1)
    if fault == "invalid_team":
        data["samples"][1]["team"] = "unknown"
    if fault == "stale":
        data["tracking_version"] = "0" * 64
    if fault == "missing_track":
        data["samples"][1]["track_id"] = 9999
    response = client.put(endpoint(tracks), headers=coach_headers, json=data)
    assert response.status_code == (
        {"stale": 409, "missing_track": 404}.get(fault, 422)
    )
    with create_session_factory(engine)() as session:
        assert session.scalar(select(TeamColorSet)) is None


def test_clearing_retains_prototype_history(client, tracks, coach_headers, engine):
    save(client, tracks, coach_headers)
    assert client.delete(endpoint(tracks), headers=coach_headers).status_code == 204
    assert client.get(endpoint(tracks), headers=coach_headers).json()["current"] is None
    with create_session_factory(engine)() as session:
        assert session.scalar(select(TeamColorSet)).is_active is False


def test_poor_examples_and_overlapping_team_colors_are_rejected(settings):
    with pytest.raises(ValueError):
        fit_prototype([Appearance((50, 0, 0), 0.2)], settings)
    with pytest.raises(ValueError):
        validate_prototypes(
            {
                TrackTeam.TEAM_A: Appearance((50, 0, 0), 1),
                TrackTeam.TEAM_B: Appearance((51, 1, 1), 1),
            }
        )


def test_seeded_classification_keeps_ambiguous_and_insufficient_evidence_unknown(
    settings,
):
    a, b = Appearance((40, 40, 30), 1), Appearance((40, -40, -30), 1)
    result = classify_seeded(
        {
            1: [a] * 3,
            2: [b] * 3,
            3: [a],
            4: [Appearance((40, 0, 0), 1)] * 3,
            5: [a, b, a, b],
        },
        {TrackTeam.TEAM_A: a, TrackTeam.TEAM_B: b},
        settings,
    )
    assert [p.team for p in result] == [
        "team_a",
        "team_b",
        "unknown",
        "unknown",
        "unknown",
    ]
    assert all(p.rejection_reason for p in result[2:])


def test_seeded_consensus_rejects_background_without_inventing_samples(settings):
    a, b = Appearance((40, 40, 30), 1), Appearance((40, -40, -30), 1)
    poor = Appearance((60, 0, 0), 0.2)
    result = classify_seeded(
        {1: [a, poor, a, poor, a], 2: [a, a, poor], 3: [a, a, a, b]},
        {TrackTeam.TEAM_A: a, TrackTeam.TEAM_B: b},
        settings,
    )
    assert result[0].team == "team_a" and result[0].accepted_sample_count == 3
    assert result[0].rejected_sample_count == 2 and result[0].sample_count == 5
    assert result[1].team == "unknown"  # Two real samples never become three.
    assert result[2].team == "unknown"  # A confident contradiction stays visible.


def test_seeded_votes_accept_typical_crops_that_clearly_match_one_kit(settings):
    # Typical real crops: 70% coherent colour, 6.4 Lab units from kit A, 52 from B.
    # The former quality x margin x closeness product (0.7 x 0.88 x 0.74 = 0.46)
    # rejected this repeated, unopposed evidence.
    a, b = Appearance((40, 30, -30), 1), Appearance((80, 0, 0), 1)
    typical = Appearance((44, 26, -27), 0.7)
    (row,) = classify_seeded(
        {1: [typical] * 4}, {TrackTeam.TEAM_A: a, TrackTeam.TEAM_B: b}, settings
    )
    assert row.team == "team_a" and row.rejection_reason is None
    assert (row.accepted_sample_count, row.rejected_sample_count) == (4, 0)
    assert row.confidence == 1
    near = ((44 - 40) ** 2 + 4**2 + 3**2) ** 0.5
    far = ((44 - 80) ** 2 + 26**2 + 27**2) ** 0.5
    assert row.margin == pytest.approx(1 - near / far)


@pytest.mark.parametrize(
    "color,quality",
    [
        ((52, 15, -15), 0.9),  # 24 Lab units from A, 35 from B: not twice as close
        ((10, 45, -55), 0.9),  # 42 from A, beyond the same-colour tolerance
        ((42, 29, -29), 0.4),  # matches A but most pixels are another colour
    ],
)
def test_seeded_votes_abstain_on_ambiguous_distant_or_incoherent_crops(
    settings, color, quality
):
    a, b = Appearance((40, 30, -30), 1), Appearance((80, 0, 0), 1)
    (row,) = classify_seeded(
        {1: [Appearance(color, quality)] * 5},
        {TrackTeam.TEAM_A: a, TrackTeam.TEAM_B: b},
        settings,
    )
    assert row.team == "unknown"
    assert row.rejection_reason == "insufficient_consistent_samples"
    assert row.accepted_sample_count == 0 and row.confidence == 0


def test_seeded_confidence_is_the_share_of_samples_that_voted(settings):
    a, b = Appearance((40, 30, -30), 1), Appearance((80, 0, 0), 1)
    ambiguous = Appearance((60, 15, -15), 0.9)
    (row,) = classify_seeded(
        {1: [a, a, ambiguous, a, ambiguous]},
        {TrackTeam.TEAM_A: a, TrackTeam.TEAM_B: b},
        settings,
    )
    assert row.team == "team_a"
    assert row.confidence == pytest.approx(3 / 5)
    assert (row.accepted_sample_count, row.rejected_sample_count) == (3, 2)


def test_downgrade_refuses_to_discard_even_retired_prototype_history(
    client, tracks, coach_headers, engine
):
    from conftest import migration_config

    from alembic import command

    saved = save(client, tracks, coach_headers)
    assert client.delete(endpoint(tracks), headers=coach_headers).status_code == 204
    with engine.begin() as connection:
        with pytest.raises(RuntimeError, match="team-color prototype history"):
            command.downgrade(
                migration_config(connection), "0014_signup_requested_role"
            )
    with create_session_factory(engine)() as session:
        row = session.scalar(select(TeamColorSet))
        assert row is not None and row.is_active is False
        assert len(row.samples) == len(saved["current"]["samples"])
