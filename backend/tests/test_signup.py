"""Synthetic accounts in disposable databases; no email or CV processing."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import TEST_PASSWORD, migration_config
from sqlalchemy import func, inspect, select, text

from alembic import command
from app.auth.passwords import verify_password
from app.auth.tokens import create_access_token
from app.database.session import create_session_factory
from app.models.football import ClubMembership
from app.models.signup_request import SignupRequest
from app.models.user import User
from app.schemas.signup import SignupApproval, SignupCreate
from app.schemas.user import UserCreate
from app.services.domain_common import DomainError
from app.services.signup_service import approve_request, reject_request, submit_signup
from app.services.user_service import create_user

PAYLOAD = {
    "full_name": "New Applicant",
    "email": "new@example.com",
    "password": TEST_PASSWORD,
    "requested_role": "coach",
}


def submit(client, session, **changes):
    response = client.post("/api/auth/signup", json={**PAYLOAD, **changes})
    assert response.status_code == 202, response.text
    request_id = session.scalar(
        select(SignupRequest.id).where(
            SignupRequest.email
            == changes.get("email", PAYLOAD["email"]).strip().lower()
        )
    )
    session.rollback()
    return request_id


def login(client):
    return client.post(
        "/api/auth/login", json={"email": PAYLOAD["email"], "password": TEST_PASSWORD}
    )


def test_signup_waits_for_approval_and_keeps_credentials_private(
    client, session, admin_headers
):
    request_id = submit(
        client, session, email="  NEW@EXAMPLE.COM  ", full_name="  New Applicant  "
    )
    request = session.get(SignupRequest, request_id)
    assert (request.email, request.full_name, request.status) == (
        "new@example.com",
        "New Applicant",
        "pending",
    )
    assert request.hashed_password != TEST_PASSWORD
    assert verify_password(TEST_PASSWORD, request.hashed_password)
    assert session.scalar(select(User).where(User.email == request.email)) is None
    assert request.reviewed_at is None
    session.rollback()
    assert login(client).status_code == 401
    response = client.get("/api/signup-requests", headers=admin_headers)
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["items"][0]["status"] == "pending"
    assert "password" not in response.text
    assert "argon2" not in response.text
    assert "access_token" not in response.text


def test_duplicate_submissions_do_not_replace_credentials_or_reveal_accounts(
    client, session, admin
):
    first = client.post("/api/auth/signup", json=PAYLOAD)
    request = session.scalar(select(SignupRequest))
    original = request.hashed_password
    session.rollback()
    for email in (" NEW@EXAMPLE.COM ", admin.email):
        result = client.post(
            "/api/auth/signup",
            json={
                **PAYLOAD,
                "email": email,
                "password": "Different-password-123",
                "full_name": "Imposter",
                "requested_role": "player",
            },
        )
        assert result.status_code == first.status_code == 202
        assert result.json() == first.json()
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(SignupRequest)) == 1
    assert request.hashed_password == original
    assert request.full_name == PAYLOAD["full_name"]
    assert request.requested_role == "coach"
    assert verify_password(TEST_PASSWORD, session.get(User, admin.id).hashed_password)


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "invalid"},
        {"full_name": " "},
        {"full_name": "x" * 201},
        {"password": "short"},
        {"password": "x" * 129},
        {"roles": ["admin"]},
        {"is_active": True},
        {"club_id": 1},
        {"status": "approved"},
        {"hashed_password": "not-a-hash"},
    ],
)
def test_public_signup_rejects_invalid_input_and_access_fields(
    client, session, changes
):
    response = client.post("/api/auth/signup", json={**PAYLOAD, **changes})
    assert response.status_code == 422
    assert TEST_PASSWORD not in response.text
    assert session.scalar(select(func.count()).select_from(SignupRequest)) == 0
    assert session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    "role", [None, "coach", "analyst", "club_management", "player"]
)
def test_only_admin_can_list_approve_or_reject(client, session, settings, role):
    request_id = submit(client, session)
    headers = {}
    if role:
        actor = create_user(
            session,
            UserCreate(
                email=f"{role}@example.com",
                full_name="Non administrator",
                password=TEST_PASSWORD,
                roles=[role],
            ),
        )
        headers = {"Authorization": f"Bearer {create_access_token(actor.id, settings)}"}
        session.commit()
    expected = 403 if role else 401
    assert client.get("/api/signup-requests", headers=headers).status_code == expected
    assert (
        client.post(
            f"/api/signup-requests/{request_id}/approve",
            headers=headers,
            json={"roles": ["admin"]},
        ).status_code
        == expected
    )
    assert (
        client.post(
            f"/api/signup-requests/{request_id}/reject", headers=headers
        ).status_code
        == expected
    )
    session.expire_all()
    assert session.get(SignupRequest, request_id).status == "pending"


def test_approval_creates_normal_account_with_only_selected_roles_and_club(
    client, session, admin, admin_headers
):
    clubs = [
        client.post("/api/clubs", headers=admin_headers, json={"name": name}).json()
        for name in ("Approved Club", "Other Club")
    ]
    request_id = submit(client, session)
    response = client.post(
        f"/api/signup-requests/{request_id}/approve",
        headers=admin_headers,
        json={"roles": ["coach"], "club_id": clubs[0]["id"]},
    )
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["roles"] == ["coach"]
    assert user["is_active"] is True
    assert "password" not in response.text
    request = session.get(SignupRequest, request_id)
    assert request.status == "approved"
    assert request.hashed_password is None
    assert request.approved_user_id == user["id"]
    assert request.reviewed_by_user_id == admin.id
    assert request.reviewed_at.tzinfo is not None
    assert (
        session.scalar(
            select(ClubMembership.club_id).where(ClubMembership.user_id == user["id"])
        )
        == clubs[0]["id"]
    )
    session.rollback()
    signed_in = login(client)
    assert signed_in.status_code == 200
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["id"] == user["id"]
    assert client.get("/api/clubs", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/clubs/{clubs[1]['id']}", headers=headers).status_code == 404
    )
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.get("/api/signup-requests", headers=headers).status_code == 403


@pytest.mark.parametrize("role", ["coach", "analyst", "player", "club_management"])
def test_approval_without_club_does_not_invent_membership(
    client, session, admin_headers, role
):
    request_id = submit(client, session, requested_role=role)
    response = client.post(
        f"/api/signup-requests/{request_id}/approve",
        headers=admin_headers,
        json={"roles": [role]},
    )
    assert response.status_code == 201
    assert response.json()["roles"] == [role]
    assert session.scalar(select(func.count()).select_from(ClubMembership)) == 0
    session.rollback()
    assert login(client).status_code == 200


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"roles": []}, 422),
        ({"roles": ["admin"]}, 422),
        ({"roles": ["analyst"]}, 422),
        ({"roles": ["coach", "analyst"]}, 422),
        ({"roles": ["superuser"]}, 422),
        ({"roles": ["coach", "coach"]}, 422),
        ({}, 422),
        ({"roles": ["coach"], "club_id": 9999}, 404),
        ({"roles": ["coach"], "password": "overwrite"}, 422),
    ],
)
def test_invalid_approval_leaves_request_pending(
    client, session, admin_headers, payload, expected
):
    request_id = submit(client, session)
    result = client.post(
        f"/api/signup-requests/{request_id}/approve",
        headers=admin_headers,
        json=payload,
    )
    assert result.status_code == expected, result.text
    assert session.get(SignupRequest, request_id).status == "pending"
    assert session.scalar(select(User).where(User.email == PAYLOAD["email"])) is None


def test_inactive_club_cannot_be_assigned(client, session, admin_headers):
    club = client.post(
        "/api/clubs", json={"name": "Retired Club"}, headers=admin_headers
    ).json()
    assert (
        client.patch(
            f"/api/clubs/{club['id']}", json={"is_active": False}, headers=admin_headers
        ).status_code
        == 200
    )
    request_id = submit(client, session)
    result = client.post(
        f"/api/signup-requests/{request_id}/approve",
        json={"roles": ["coach"], "club_id": club["id"]},
        headers=admin_headers,
    )
    assert result.status_code == 409
    assert session.get(SignupRequest, request_id).status == "pending"


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_review_is_final_and_rejection_grants_no_access(
    client, session, admin_headers, action
):
    request_id = submit(client, session)
    args = {"json": {"roles": ["coach"]}} if action == "approve" else {}
    result = client.post(
        f"/api/signup-requests/{request_id}/{action}", headers=admin_headers, **args
    )
    assert result.status_code == (201 if action == "approve" else 200)
    assert "password" not in result.text
    for next_action in ("approve", "reject"):
        response = client.post(
            f"/api/signup-requests/{request_id}/{next_action}",
            headers=admin_headers,
            json={"roles": ["coach"]},
        )
        assert response.status_code == 409
    assert login(client).status_code == (200 if action == "approve" else 401)
    assert client.post("/api/auth/signup", json=PAYLOAD).status_code == 202
    reviewed = session.get(SignupRequest, request_id)
    assert reviewed.status == ("approved" if action == "approve" else "rejected")
    assert reviewed.hashed_password is None
    if action == "reject":
        assert (
            session.scalar(select(User).where(User.email == PAYLOAD["email"])) is None
        )


def test_account_created_since_request_is_never_overwritten(
    client, session, admin_headers
):
    request_id = submit(client, session)
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "email": PAYLOAD["email"],
            "full_name": PAYLOAD["full_name"],
            "password": "Other-password-123",
            "roles": ["player"],
        },
    )
    assert created.status_code == 201
    result = client.post(
        f"/api/signup-requests/{request_id}/approve",
        headers=admin_headers,
        json={"roles": ["coach"]},
    )
    assert result.status_code == 409
    user = session.get(User, created.json()["id"])
    assert [role.name for role in user.roles] == ["player"]
    assert verify_password("Other-password-123", user.hashed_password)
    assert session.get(SignupRequest, request_id).status == "pending"


def test_history_filters_pagination_and_missing_requests(
    client, session, admin_headers
):
    for i in range(3):
        submit(client, session, email=f"new{i}@example.com")
    path = "/api/signup-requests"
    first = client.get(path + "?limit=1", headers=admin_headers).json()
    second = client.get(path + "?limit=1&offset=1", headers=admin_headers).json()
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["id"] != second["items"][0]["id"]
    request_id = first["items"][0]["id"]
    assert (
        client.post(f"{path}/{request_id}/reject", headers=admin_headers).status_code
        == 200
    )
    assert client.get(path, headers=admin_headers).json()["total"] == 2
    history = client.get(path + "?status=rejected", headers=admin_headers).json()
    assert history["total"] == 1
    assert history["items"][0]["reviewed_at"]
    assert (
        client.get(path + "?status=anything", headers=admin_headers).status_code == 422
    )
    assert client.post(path + "/9999/reject", headers=admin_headers).status_code == 404


@pytest.mark.parametrize("second_action", ["approve", "reject"])
def test_concurrent_reviews_publish_only_one_decision(
    client, session, engine, admin, second_action
):
    request_id = submit(client, session)
    actor_id = admin.id
    session.rollback()
    barrier = Barrier(2)
    factory = create_session_factory(engine)

    def review(action):
        with factory() as concurrent:
            actor = concurrent.get(User, actor_id)
            barrier.wait(timeout=10)
            try:
                if action == "approve":
                    approve_request(
                        concurrent, actor, request_id, SignupApproval(roles=["coach"])
                    )
                else:
                    reject_request(concurrent, actor, request_id)
                return 200
            except DomainError as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(review, ["approve", second_action]))
    assert sorted(outcomes) == [200, 409]
    request = session.get(SignupRequest, request_id)
    count = session.scalar(
        select(func.count()).select_from(User).where(User.email == PAYLOAD["email"])
    )
    assert count == (1 if request.status == "approved" else 0)
    assert request.hashed_password is None


def test_concurrent_public_duplicate_creates_one_request(engine):
    factory = create_session_factory(engine)
    barrier = Barrier(2)

    def signup(_):
        with factory() as concurrent:
            barrier.wait(timeout=10)
            submit_signup(concurrent, SignupCreate(**PAYLOAD))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(signup, range(2)))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SignupRequest)) == 1


def test_signup_migration_preserves_existing_account(engine, admin, session):
    actor_id, original_hash = admin.id, admin.hashed_password
    session.rollback()
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0012_match_reports")
        assert "signup_requests" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0015_team_color_prototypes"
        )
        assert (
            connection.scalar(
                text("SELECT hashed_password FROM users WHERE id=:id"), {"id": actor_id}
            )
            == original_hash
        )
        assert connection.scalar(text("SELECT count(*) FROM roles")) == 5
        command.check(config)


@pytest.mark.parametrize("role", ["coach", "analyst", "player", "club_management"])
def test_requested_role_is_saved_and_visible_without_granting_access(
    client, session, admin_headers, role
):
    request_id = submit(client, session, requested_role=role)
    request = session.get(SignupRequest, request_id)
    assert request.requested_role == role
    assert request.status == "pending"
    assert session.scalar(select(User).where(User.email == PAYLOAD["email"])) is None
    session.rollback()
    listed = client.get("/api/signup-requests", headers=admin_headers).json()
    assert listed["items"][0]["requested_role"] == role
    assert login(client).status_code == 401
    approved = client.post(
        f"/api/signup-requests/{request_id}/approve",
        headers=admin_headers,
        json={"roles": [role]},
    )
    assert approved.status_code == 201
    assert approved.json()["roles"] == [role]
    history = client.get(
        "/api/signup-requests?status=approved", headers=admin_headers
    ).json()
    assert history["items"][0]["requested_role"] == role
    assert login(client).status_code == 200


@pytest.mark.parametrize(
    "role", ["admin", "Admin", "superuser", "", None, 1, ["coach"]]
)
def test_public_signup_cannot_request_admin_or_invalid_roles(client, session, role):
    response = client.post("/api/auth/signup", json={**PAYLOAD, "requested_role": role})
    assert response.status_code == 422
    assert TEST_PASSWORD not in response.text
    assert session.scalar(select(func.count()).select_from(SignupRequest)) == 0
    assert session.scalar(select(func.count()).select_from(User)) == 0


def test_public_signup_requires_role_and_documents_only_non_admin_choices(client):
    payload = {key: value for key, value in PAYLOAD.items() if key != "requested_role"}
    response = client.post("/api/auth/signup", json=payload)
    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", "requested_role"]
        for error in response.json()["detail"]
    )
    schema = client.get("/openapi.json").json()["components"]["schemas"]["SignupCreate"]
    assert "requested_role" in schema["required"]
    assert set(schema["properties"]["requested_role"]["enum"]) == {
        "coach",
        "analyst",
        "player",
        "club_management",
    }


def test_approval_cannot_substitute_a_different_role(client, session, admin_headers):
    request_id = submit(client, session, requested_role="coach")
    for roles in (["club_management"], ["admin"], ["coach", "analyst"]):
        result = client.post(
            f"/api/signup-requests/{request_id}/approve",
            headers=admin_headers,
            json={"roles": roles},
        )
        assert result.status_code == 422
    assert session.get(SignupRequest, request_id).status == "pending"
    assert session.scalar(select(User).where(User.email == PAYLOAD["email"])) is None
    session.rollback()
    result = client.post(
        f"/api/signup-requests/{request_id}/approve",
        headers=admin_headers,
        json={"roles": ["coach"]},
    )
    assert result.status_code == 201
    assert result.json()["roles"] == ["coach"]


def test_requested_role_migration_preserves_legacy_requests_and_restricts_admin(
    engine, session, admin, client, admin_headers
):
    from sqlalchemy.exc import IntegrityError

    original_hash, actor_id = admin.hashed_password, admin.id
    session.rollback()
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0013_signup_requests")
        connection.execute(
            text(
                "INSERT INTO signup_requests (email, full_name, hashed_password) "
                "VALUES (:email, :name, :hashed)"
            ),
            {
                "email": "legacy@example.com",
                "name": "Legacy Applicant",
                "hashed": original_hash,
            },
        )
        connection.execute(
            text(
                "INSERT INTO signup_requests (email, full_name, status, "
                "reviewed_at, reviewed_by_user_id) "
                "VALUES ('old-rejected@example.com', 'Old Rejected', "
                "'rejected', '2026-01-01 00:00:00', :actor)"
            ),
            {"actor": actor_id},
        )
        before = [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM signup_requests ORDER BY id")
            ).mappings()
        ]
        command.upgrade(config, "head")
        after = [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM signup_requests ORDER BY id")
            ).mappings()
        ]
        assert [{key: row[key] for key in before[0]} for row in after] == before
        assert all(row["requested_role"] is None for row in after)
        command.check(config)
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE signup_requests SET requested_role = 'admin'")
            )
        command.downgrade(config, "0013_signup_requests")
        assert [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM signup_requests ORDER BY id")
            ).mappings()
        ] == before
        command.upgrade(config, "head")
    response = client.get("/api/signup-requests", headers=admin_headers)
    assert response.status_code == 200
    legacy = response.json()["items"][0]
    assert legacy["requested_role"] is None
    approved = client.post(
        f"/api/signup-requests/{legacy['id']}/approve",
        headers=admin_headers,
        json={"roles": ["analyst"]},
    )
    assert approved.status_code == 201
    assert approved.json()["roles"] == ["analyst"]
