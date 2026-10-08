from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import TEST_PASSWORD
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.passwords import hash_password, verify_password
from app.auth.roles import RoleName
from app.auth.tokens import create_access_token
from app.core.config import Settings
from app.main import create_app
from app.models.user import User


def test_password_hashing() -> None:
    hashed = hash_password(TEST_PASSWORD)
    assert hashed != TEST_PASSWORD
    assert hashed.startswith("$argon2id$")
    assert verify_password(TEST_PASSWORD, hashed)
    assert not verify_password("wrong-password", hashed)


def test_login_and_current_user(client: TestClient, admin: User) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "ADMIN@example.com",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["access_token"]
    result = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 200
    data = result.json()
    assert data["id"] == admin.id
    assert data["roles"] == ["admin"]
    assert data["email"] == "admin@example.com"
    assert data["created_at"].endswith("Z")
    assert "password" not in result.text
    assert TEST_PASSWORD not in result.text


@pytest.mark.parametrize("scenario", ["wrong_password", "missing_user", "inactive"])
def test_bad_credentials_are_indistinguishable(
    client: TestClient, admin: User, session: Session, scenario: str
) -> None:
    if scenario == "inactive":
        admin.is_active = False
        session.commit()
    response = client.post(
        "/api/auth/login",
        json={
            "email": "missing@example.com"
            if scenario == "missing_user"
            else admin.email,
            "password": "wrong-password"
            if scenario == "wrong_password"
            else TEST_PASSWORD,
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization", [None, "Bearer garbage", "Basic Zm9vOmJhcg=="]
)
def test_missing_or_invalid_token(
    client: TestClient, authorization: str | None
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    assert client.get("/api/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "case",
    [
        "expired",
        "wrong_signature",
        "wrong_algorithm",
        "missing_exp",
        "wrong_type",
        "invalid_sub",
        "huge_sub",
        "missing_user",
        "future_iat",
    ],
)
def test_rejects_invalid_jwt_claims(
    client: TestClient, settings: Settings, admin: User, case: str
) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(admin.id),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "access",
    }
    key = settings.require_jwt_secret()
    algorithm = "HS256"
    if case == "expired":
        payload["exp"] = now - timedelta(seconds=1)
    if case == "wrong_signature":
        key = "a-different-test-only-secret-long-enough-1234567"
    if case == "wrong_algorithm":
        algorithm = "HS512"
    if case == "missing_exp":
        del payload["exp"]
    if case == "wrong_type":
        payload["type"] = "refresh"
    if case == "invalid_sub":
        payload["sub"] = "not-an-id"
    if case == "huge_sub":
        payload["sub"] = "9" * 200
    if case == "missing_user":
        payload["sub"] = "999999"
    if case == "future_iat":
        payload["iat"] = now + timedelta(days=1)
    token = jwt.encode(payload, key, algorithm=algorithm)
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_deactivation_blocks_existing_token(
    client: TestClient, coach: User, coach_headers: dict, admin_headers: dict
) -> None:
    response = client.patch(
        f"/api/users/{coach.id}", json={"is_active": False}, headers=admin_headers
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=coach_headers).status_code == 401


def test_role_changes_apply_to_existing_token(
    client: TestClient, coach: User, coach_headers: dict, admin_headers: dict
) -> None:
    assert client.get("/api/users", headers=coach_headers).status_code == 403
    assert (
        client.patch(
            f"/api/users/{coach.id}", json={"roles": ["admin"]}, headers=admin_headers
        ).status_code
        == 200
    )
    assert client.get("/api/users", headers=coach_headers).status_code == 200
    assert (
        client.patch(
            f"/api/users/{coach.id}", json={"roles": ["coach"]}, headers=admin_headers
        ).status_code
        == 200
    )
    assert client.get("/api/users", headers=coach_headers).status_code == 403


def test_any_role_dependency(client: TestClient, coach_headers: dict) -> None:
    @client.app.get(
        "/test-analysis",
        dependencies=[Depends(require_roles(RoleName.COACH, RoleName.ANALYST))],
    )
    def analysis_access() -> dict:
        return {"allowed": True}

    assert client.get("/test-analysis", headers=coach_headers).status_code == 200


@pytest.mark.parametrize(
    "secret", [None, "short", "replace-with-a-secure-random-secret", "a" * 64]
)
def test_startup_requires_strong_secret(settings: Settings, secret: str | None) -> None:
    settings.jwt_secret = SecretStr(secret) if secret else None
    with (
        pytest.raises(ValueError, match="JWT_SECRET"),
        TestClient(create_app(settings)),
    ):
        pass


def test_token_subject_is_user_id(settings: Settings, admin: User) -> None:
    token = create_access_token(admin.id, settings)
    claims = jwt.decode(token, settings.require_jwt_secret(), algorithms=["HS256"])
    assert claims["sub"] == str(admin.id)
    assert claims["exp"] - claims["iat"] == settings.access_token_expire_minutes * 60
