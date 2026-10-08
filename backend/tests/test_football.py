"""Synthetic, isolated API fixtures exercise capability and club boundaries."""

import pytest
from conftest import TEST_PASSWORD, migration_config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command


@pytest.fixture
def domain(client, admin_headers, coach, coach_headers):
    def post(path, payload, headers=admin_headers):
        response = client.post(f"/api/{path}", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    clubs = [post("clubs", {"name": name}) for name in ("North", "South")]
    post(f"clubs/{clubs[0]['id']}/members", {"user_id": coach.id})
    teams = [
        post("teams", {"club_id": club["id"], "name": name})
        for club in clubs
        for name in ("First XI", "Reserves")
    ]
    players = [
        post(
            "players", {"club_id": club["id"], "first_name": "Test", "last_name": name}
        )
        for club, name in zip(clubs, ("North", "South"), strict=True)
    ]
    squad = post(
        f"teams/{teams[0]['id']}/squad",
        {"player_id": players[0]["id"], "shirt_number": 9},
        coach_headers,
    )
    matches = [
        post(
            "matches",
            {
                "club_id": club["id"],
                "title": f"{club['name']} fixture",
                "team_a_id": teams[index * 2]["id"],
                "team_b_id": teams[index * 2 + 1]["id"],
                "match_format": "11v11",
                "match_date": "2026-09-01T17:00:00+05:00",
                "pitch_length_metres": 105,
                "pitch_width_metres": 68,
            },
            coach_headers if index == 0 else admin_headers,
        )
        for index, club in enumerate(clubs)
    ]
    return {
        "clubs": clubs,
        "teams": teams,
        "players": players,
        "matches": matches,
        "squad": squad,
        "post": post,
    }


def role_account(client, domain, role, club_index=0):
    account = domain["post"](
        "users",
        {
            "email": f"{role}@example.com",
            "full_name": f"Test {role}",
            "password": TEST_PASSWORD,
            "roles": [role],
        },
    )
    domain["post"](
        f"clubs/{domain['clubs'][club_index]['id']}/members", {"user_id": account["id"]}
    )
    token = client.post(
        "/api/auth/login", json={"email": account["email"], "password": TEST_PASSWORD}
    ).json()["access_token"]
    return account, {"Authorization": f"Bearer {token}"}


def test_complete_coach_workflow_and_scoped_counts(client, domain, coach_headers):
    for resource in ("clubs", "players", "matches"):
        result = client.get(f"/api/{resource}?limit=1", headers=coach_headers).json()
        assert result["total"] == 1
        assert result["items"][0]["id"] == domain[resource][0]["id"]
    result = client.get("/api/teams?offset=1&limit=1", headers=coach_headers).json()
    assert result["total"] == 2 and len(result["items"]) == 1
    match = domain["matches"][0]
    assert match["match_date"] == "2026-09-01T12:00:00Z"
    assert match["pitch_length_metres"] == 105
    assert "password" not in str(domain)


@pytest.mark.parametrize(
    "resource,index", [("clubs", 1), ("teams", 2), ("players", 1), ("matches", 1)]
)
def test_detail_and_patch_cannot_cross_clubs(
    client, domain, coach_headers, resource, index
):
    record_id = domain[resource][index]["id"]
    assert (
        client.get(f"/api/{resource}/{record_id}", headers=coach_headers).status_code
        == 404
    )
    payload = {"is_archived": True} if resource == "matches" else {"is_active": False}
    expected = 403 if resource == "clubs" else 404
    assert (
        client.patch(
            f"/api/{resource}/{record_id}", json=payload, headers=coach_headers
        ).status_code
        == expected
    )


def test_filters_and_nested_routes_do_not_bypass_scope(client, domain, coach_headers):
    foreign_club = domain["clubs"][1]["id"]
    foreign_team = domain["teams"][2]["id"]
    for path in (
        f"teams?club_id={foreign_club}",
        f"players?team_id={foreign_team}",
        f"matches?team_id={foreign_team}",
        f"teams/{foreign_team}/squad",
        f"players/{domain['players'][1]['id']}/squads",
    ):
        assert client.get(f"/api/{path}", headers=coach_headers).status_code == 404
    wrong_team = domain["teams"][1]["id"]
    assert (
        client.delete(
            f"/api/teams/{wrong_team}/squad/{domain['squad']['id']}",
            headers=coach_headers,
        ).status_code
        == 404
    )


@pytest.mark.parametrize("role", ["analyst", "club_management", "player"])
def test_roles_cannot_modify_rosters_or_assign_clubs(client, domain, role):
    _, headers = role_account(client, domain, role)
    club = domain["clubs"][0]["id"]
    team = domain["teams"][0]["id"]
    for method, path, data in (
        ("POST", "clubs", {"name": "Forbidden"}),
        ("PATCH", f"clubs/{club}", {"name": "Forbidden"}),
        ("POST", f"clubs/{club}/members", {"user_id": 999}),
        ("POST", "teams", {"club_id": club, "name": "Forbidden"}),
        ("PATCH", f"teams/{team}", {"name": "Forbidden"}),
        (
            "POST",
            "players",
            {"club_id": club, "first_name": "No", "last_name": "Write"},
        ),
        ("PATCH", f"players/{domain['players'][0]['id']}", {"is_active": False}),
        ("POST", f"teams/{team}/squad", {"player_id": domain["players"][0]["id"]}),
        ("DELETE", f"teams/{team}/squad/{domain['squad']['id']}", None),
    ):
        assert (
            client.request(
                method, f"/api/{path}", json=data, headers=headers
            ).status_code
            == 403
        )
    assert client.get(f"/api/clubs/{club}/members", headers=headers).status_code == 403
    match_id = domain["matches"][0]["id"]
    result = client.patch(
        f"/api/matches/{match_id}", json={"notes": "Reviewed"}, headers=headers
    )
    assert result.status_code == (200 if role == "analyst" else 403)
    if role != "player":
        assert client.get("/api/teams", headers=headers).json()["total"] == 2


def test_membership_revocation_and_inactive_club_revoke_existing_token(
    client, domain, coach, coach_headers, admin_headers
):
    club = domain["clubs"][0]["id"]
    assert (
        client.delete(
            f"/api/clubs/{club}/members/{coach.id}", headers=admin_headers
        ).status_code
        == 204
    )
    assert client.get("/api/matches", headers=coach_headers).json()["total"] == 0
    domain["post"](f"clubs/{club}/members", {"user_id": coach.id})
    assert (
        client.patch(
            f"/api/clubs/{club}", json={"is_active": False}, headers=admin_headers
        ).status_code
        == 200
    )
    assert client.get("/api/teams", headers=coach_headers).json()["total"] == 0
    assert client.get("/api/teams", headers=admin_headers).json()["total"] == 4
    assert (
        client.post(
            "/api/teams",
            json={"club_id": club, "name": "Inactive"},
            headers=admin_headers,
        ).status_code
        == 409
    )


def test_linked_player_sees_only_own_profile_current_team_and_relevant_matches(
    client, domain, admin_headers
):
    account, headers = role_account(client, domain, "player")
    assert client.get("/api/players", headers=headers).json()["items"] == []
    own = domain["players"][0]["id"]
    assert (
        client.patch(
            f"/api/players/{own}",
            json={"user_id": account["id"]},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert client.get("/api/players", headers=headers).json()["total"] == 1
    assert client.get("/api/teams", headers=headers).json()["total"] == 1
    assert client.get("/api/matches", headers=headers).json()["total"] == 1
    club = domain["clubs"][0]["id"]
    peer = domain["post"](
        "players", {"club_id": club, "first_name": "Other", "last_name": "Person"}
    )
    team = domain["teams"][0]["id"]
    domain["post"](f"teams/{team}/squad", {"player_id": peer["id"]})
    assert client.get(f"/api/players/{peer['id']}", headers=headers).status_code == 404
    squad = client.get(f"/api/teams/{team}/squad", headers=headers).json()
    assert squad["total"] == 1 and squad["items"][0]["player_id"] == own
    assert (
        client.get(
            f"/api/teams/{domain['teams'][1]['id']}", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/teams/{team}/squad/{domain['squad']['id']}", headers=admin_headers
        ).status_code
        == 204
    )
    assert client.get("/api/teams", headers=headers).json()["total"] == 0
    assert client.get("/api/matches", headers=headers).json()["total"] == 0
    assert (
        client.get(f"/api/players/{own}/squads", headers=headers).json()["total"] == 0
    )


def test_player_account_link_unique_optional_and_club_scoped(
    client, domain, admin_headers
):
    account, _ = role_account(client, domain, "player")
    player = domain["players"][0]["id"]
    assert (
        client.patch(
            f"/api/players/{player}",
            json={"user_id": account["id"]},
            headers=admin_headers,
        ).status_code
        == 200
    )
    club = domain["clubs"][0]["id"]
    payload = {
        "club_id": club,
        "first_name": "Duplicate",
        "last_name": "Link",
        "user_id": account["id"],
    }
    assert (
        client.post("/api/players", json=payload, headers=admin_headers).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/players/{domain['players'][1]['id']}",
            json={"user_id": account["id"]},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/players/{player}", json={"user_id": None}, headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        client.post("/api/players", json=payload, headers=admin_headers).status_code
        == 201
    )
    options = client.get(
        f"/api/clubs/{club}/player-account-options", headers=admin_headers
    ).json()
    assert all(set(item) == {"id", "full_name"} for item in options["items"])


def test_squad_conflicts_soft_removal_history_and_rejoining(
    client, domain, coach_headers
):
    team = domain["teams"][0]["id"]
    squad = domain["squad"]
    path = f"/api/teams/{team}/squad"
    assert (
        client.post(
            path, json={"player_id": squad["player_id"]}, headers=coach_headers
        ).status_code
        == 409
    )
    other = domain["post"](
        "players",
        {
            "club_id": domain["clubs"][0]["id"],
            "first_name": "Other",
            "last_name": "Forward",
        },
    )
    assert (
        client.post(
            path,
            json={"player_id": other["id"], "shirt_number": 9},
            headers=coach_headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            path, json={"player_id": domain["players"][1]["id"]}, headers=coach_headers
        ).status_code
        == 422
    )
    assert (
        client.delete(f"{path}/{squad['id']}", headers=coach_headers).status_code == 204
    )
    history = client.get(path, headers=coach_headers).json()["items"][0]
    assert not history["is_active"] and history["left_at"]
    assert (
        client.patch(
            f"{path}/{squad['id']}", json={"is_active": True}, headers=coach_headers
        ).status_code
        == 409
    )
    joined = client.post(
        path,
        json={"player_id": squad["player_id"], "shirt_number": 9},
        headers=coach_headers,
    )
    assert joined.status_code == 201 and joined.json()["id"] != squad["id"]
    assert client.get(path, headers=coach_headers).json()["total"] == 2
    assert client.get(f"{path}?active=true", headers=coach_headers).json()["total"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"match_format": "7v7"},
        {"pitch_length_metres": 0},
        {"pitch_width_metres": -1},
        {"pitch_length_metres": 151},
        {"pitch_width_metres": 101},
        {"pitch_length_metres": 20},
        {"match_date": "2026-09-01T12:00:00"},
        {"title": " "},
        {"club_id": 2},
        {"created_by_user_id": 2},
        {"team_a_id": None},
        {},
    ],
)
def test_match_update_validation(client, domain, coach_headers, changes):
    match = domain["matches"][0]["id"]
    assert (
        client.patch(
            f"/api/matches/{match}", json=changes, headers=coach_headers
        ).status_code
        == 422
    )


def test_match_team_integrity_archive_and_custom_dimensions(
    client, domain, coach_headers
):
    record = domain["matches"][0]
    path = f"/api/matches/{record['id']}"
    for team in (record["team_a_id"], domain["teams"][2]["id"]):
        assert (
            client.patch(
                path, json={"team_b_id": team}, headers=coach_headers
            ).status_code
            == 422
        )
    updated = client.patch(
        path,
        json={
            "match_format": "5v5",
            "pitch_length_metres": 42,
            "pitch_width_metres": 22,
            "is_archived": True,
        },
        headers=coach_headers,
    )
    assert updated.status_code == 200 and updated.json()["pitch_length_metres"] == 42
    assert (
        client.get("/api/matches?archived=false", headers=coach_headers).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/api/matches?archived=true&match_format=5v5", headers=coach_headers
        ).json()["total"]
        == 1
    )
    assert client.delete(path, headers=coach_headers).status_code == 405


def test_names_and_player_validation(client, domain, admin_headers):
    assert (
        client.post(
            "/api/clubs", json={"name": " north "}, headers=admin_headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/teams",
            json={"club_id": domain["clubs"][0]["id"], "name": " FIRST XI "},
            headers=admin_headers,
        ).status_code
        == 409
    )
    player = domain["players"][0]["id"]
    for payload in (
        {"date_of_birth": "2999-01-01"},
        {"preferred_position": "striker"},
        {"first_name": " "},
        {"club_id": 2},
    ):
        assert (
            client.patch(
                f"/api/players/{player}", json=payload, headers=admin_headers
            ).status_code
            == 422
        )
    for resource in ("clubs", "teams", "players"):
        assert (
            client.delete(
                f"/api/{resource}/{domain[resource][0]['id']}", headers=admin_headers
            ).status_code
            == 405
        )


@pytest.mark.parametrize(
    "path",
    [
        "clubs",
        "teams",
        "players",
        "matches",
        "teams/1/squad",
        "players/1/squads",
        "clubs/1/members",
    ],
)
def test_domain_requires_authentication(client, path):
    assert client.get(f"/api/{path}").status_code == 401


def test_database_rejects_cross_club_and_invalid_match_writes(engine, domain):
    match = domain["matches"][0]["id"]
    foreign_team = domain["teams"][2]["id"]
    for column, value in (
        ("team_b_id", foreign_team),
        ("pitch_length_metres", 0),
        ("match_format", "7v7"),
        ("team_b_id", domain["teams"][0]["id"]),
    ):
        with engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(
                text(f"UPDATE matches SET {column} = :value WHERE id = :id"),
                {"value": value, "id": match},
            )
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text("UPDATE squad_memberships SET player_id = :id"),
            {"id": domain["players"][1]["id"]},
        )
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text("DELETE FROM teams WHERE id = :id"), {"id": domain["teams"][0]["id"]}
        )


def test_phase2_populated_upgrade_and_downgrade_preserve_accounts(engine, admin):
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0001_users_and_roles")
        before = connection.execute(text("SELECT * FROM users")).all()
        assignments = connection.execute(text("SELECT * FROM user_roles")).all()
        command.upgrade(config, "head")
        assert connection.execute(text("SELECT * FROM users")).all() == before
        assert connection.execute(text("SELECT * FROM user_roles")).all() == assignments
        command.check(config)
        command.downgrade(config, "0001_users_and_roles")
        assert set(inspect(connection).get_table_names()) == {
            "users",
            "roles",
            "user_roles",
            "alembic_version",
        }
        assert connection.execute(text("SELECT * FROM users")).all() == before


@pytest.mark.parametrize("resource", ["teams", "players", "matches"])
def test_create_in_unassigned_club_denied(client, domain, coach_headers, resource):
    club = domain["clubs"][1]["id"]
    payloads = {
        "teams": {"club_id": club, "name": "No access"},
        "players": {"club_id": club, "first_name": "No", "last_name": "Access"},
        "matches": {
            "club_id": club,
            "title": "No access",
            "team_a_id": domain["teams"][2]["id"],
            "team_b_id": domain["teams"][3]["id"],
            "match_format": "5v5",
            "match_date": "2026-09-01T12:00:00Z",
            "pitch_length_metres": 40,
            "pitch_width_metres": 20,
        },
    }
    assert (
        client.post(
            f"/api/{resource}", json=payloads[resource], headers=coach_headers
        ).status_code
        == 404
    )


def test_membership_duplicates_and_inactive_filters(
    client, domain, coach, admin_headers
):
    club = domain["clubs"][0]["id"]
    assert (
        client.post(
            f"/api/clubs/{club}/members",
            json={"user_id": coach.id},
            headers=admin_headers,
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/clubs/{club}", json={"is_active": False}, headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        client.get("/api/clubs?active=true", headers=admin_headers).json()["total"] == 1
    )
    assert (
        client.get("/api/clubs?active=false", headers=admin_headers).json()["items"][0][
            "id"
        ]
        == club
    )


@pytest.mark.parametrize("shirt", [0, -1, 100, 1.5])
def test_shirt_numbers_validated(client, domain, coach_headers, shirt):
    team = domain["teams"][0]["id"]
    response = client.patch(
        f"/api/teams/{team}/squad/{domain['squad']['id']}",
        json={"shirt_number": shirt},
        headers=coach_headers,
    )
    assert response.status_code == 422


def test_inactive_players_cannot_join_but_history_is_preserved(
    client, domain, coach_headers
):
    player = domain["players"][0]["id"]
    assert (
        client.patch(
            f"/api/players/{player}", json={"is_active": False}, headers=coach_headers
        ).status_code
        == 200
    )
    team = domain["teams"][1]["id"]
    assert (
        client.post(
            f"/api/teams/{team}/squad",
            json={"player_id": player},
            headers=coach_headers,
        ).status_code
        == 422
    )
    assert (
        client.get(f"/api/players/{player}/squads", headers=coach_headers).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get("/api/players?active=false", headers=coach_headers).json()["total"]
        == 1
    )
