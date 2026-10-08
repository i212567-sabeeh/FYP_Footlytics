import pytest
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.models.user import User
from app.services.user_service import get_user_by_email

NEW_USER = {
    "email": "new@example.com",
    "full_name": "New Coach",
    "password": TEST_PASSWORD,
    "roles": ["coach", "analyst"],
}


def test_create_list_and_get_user(
    client: TestClient, admin_headers: dict, session: Session
) -> None:
    response = client.post("/api/users", json=NEW_USER, headers=admin_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["roles"] == ["analyst", "coach"]
    assert "password" not in response.text
    stored = get_user_by_email(session, NEW_USER["email"])
    assert stored is not None
    assert stored.hashed_password != TEST_PASSWORD
    assert verify_password(TEST_PASSWORD, stored.hashed_password)
    result = client.get(f"/api/users/{data['id']}", headers=admin_headers)
    assert result.json() == data
    listing = client.get("/api/users?limit=1&offset=1", headers=admin_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert len(listing.json()["items"]) == 1
    assert "password" not in listing.text


def test_duplicate_email_case_insensitive(
    client: TestClient, admin_headers: dict
) -> None:
    assert (
        client.post("/api/users", json=NEW_USER, headers=admin_headers).status_code
        == 201
    )
    response = client.post(
        "/api/users",
        json={**NEW_USER, "email": "NEW@EXAMPLE.COM"},
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "invalid"},
        {"full_name": "   "},
        {"password": "short"},
        {"password": "x" * 129},
        {"roles": []},
        {"roles": ["owner"]},
        {"roles": ["coach", "coach"]},
        {"hashed_password": "do-not-accept-this-hash"},
    ],
)
def test_creation_validation(
    client: TestClient, admin_headers: dict, changes: dict
) -> None:
    payload = {**NEW_USER, **changes}
    response = client.post("/api/users", json=payload, headers=admin_headers)
    assert response.status_code == 422
    assert TEST_PASSWORD not in response.text
    assert '"input"' not in response.text
    assert "do-not-accept-this-hash" not in response.text


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/users", None),
        ("POST", "/api/users", NEW_USER),
        ("GET", "/api/users/999", None),
        ("PATCH", "/api/users/999", {"is_active": False}),
    ],
)
def test_admin_endpoints_reject_non_admin_and_anonymous(
    client: TestClient,
    coach_headers: dict,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    assert client.request(method, path, json=payload).status_code == 401
    assert (
        client.request(method, path, json=payload, headers=coach_headers).status_code
        == 403
    )


def test_update_and_reactivate(
    client: TestClient, coach: User, admin_headers: dict
) -> None:
    before = client.get(f"/api/users/{coach.id}", headers=admin_headers).json()
    result = client.patch(
        f"/api/users/{coach.id}",
        headers=admin_headers,
        json={
            "full_name": "Updated Coach",
            "email": "UPDATED@example.com",
            "is_active": False,
            "roles": ["player", "club_management"],
        },
    )
    assert result.status_code == 200
    data = result.json()
    assert data["email"] == "updated@example.com"
    assert data["full_name"] == "Updated Coach"
    assert data["roles"] == ["club_management", "player"]
    assert data["is_active"] is False
    assert data["created_at"] == before["created_at"]
    assert data["updated_at"] >= before["updated_at"]
    assert data["updated_at"].endswith("Z")
    assert (
        client.patch(
            f"/api/users/{coach.id}", headers=admin_headers, json={"is_active": True}
        ).json()["is_active"]
        is True
    )


@pytest.mark.parametrize(
    "payload", [{"email": None}, {}, {"roles": []}, {"password": "New-password"}]
)
def test_update_rejects_invalid_payload(
    client: TestClient, coach: User, admin_headers: dict, payload: dict
) -> None:
    assert (
        client.patch(
            f"/api/users/{coach.id}", json=payload, headers=admin_headers
        ).status_code
        == 422
    )


def test_update_duplicate_email_rolls_back(
    client: TestClient, coach: User, admin_headers: dict
) -> None:
    result = client.patch(
        f"/api/users/{coach.id}",
        json={"email": "ADMIN@example.com", "full_name": "Should not change"},
        headers=admin_headers,
    )
    assert result.status_code == 409
    assert (
        client.get(f"/api/users/{coach.id}", headers=admin_headers).json()["full_name"]
        == "Test Coach"
    )


def test_missing_user(client: TestClient, admin_headers: dict) -> None:
    assert client.get("/api/users/99999", headers=admin_headers).status_code == 404
    assert (
        client.patch(
            "/api/users/99999", json={"is_active": False}, headers=admin_headers
        ).status_code
        == 404
    )


@pytest.mark.parametrize("payload", [{"is_active": False}, {"roles": ["coach"]}])
def test_cannot_lock_out_own_admin(
    client: TestClient, admin: User, admin_headers: dict, payload: dict
) -> None:
    assert (
        client.patch(
            f"/api/users/{admin.id}", json=payload, headers=admin_headers
        ).status_code
        == 409
    )


def test_no_legacy_registration_route_or_user_deletion(
    client: TestClient, admin: User, admin_headers: dict
) -> None:
    assert client.post("/api/auth/register", json=NEW_USER).status_code == 404
    assert (
        client.delete(f"/api/users/{admin.id}", headers=admin_headers).status_code
        == 405
    )
