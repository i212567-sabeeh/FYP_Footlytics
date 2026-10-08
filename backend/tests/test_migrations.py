import os
import subprocess
import sys

import pytest
from conftest import TEST_PASSWORD, migration_config
from sqlalchemy import Engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import PROJECT_ROOT, Settings
from app.models.user import Role, User
from app.services.role_service import ensure_roles


def test_migration_round_trip_and_model_consistency(engine: Engine) -> None:
    with engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == {
            "users",
            "roles",
            "user_roles",
            "alembic_version",
            "clubs",
            "club_memberships",
            "teams",
            "players",
            "squad_memberships",
            "matches",
            "match_videos",
            "processing_jobs",
            "pitch_calibrations",
            "track_team_assignments",
            "signup_requests",
            "team_color_sets",
        }
        assert connection.scalar(text("SELECT count(*) FROM roles")) == 5
        command.check(config)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM roles")) == 5


def test_seeding_is_idempotent(session: Session) -> None:
    ensure_roles(session)
    ensure_roles(session)
    session.commit()
    assert set(session.scalars(select(Role.name))) == {
        "admin",
        "coach",
        "analyst",
        "player",
        "club_management",
    }
    assert session.scalar(select(func.count()).select_from(Role)) == 5


def test_sqlite_enforces_foreign_keys(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (999999, 999999)"
                )
            )


def test_create_admin_script_and_coach_workflow(
    settings: Settings, engine: Engine, client
) -> None:
    environment = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "FOOTLYTICS_ADMIN_PASSWORD": TEST_PASSWORD,
    }
    command_line = [
        sys.executable,
        str(PROJECT_ROOT / "scripts/create_admin.py"),
        "--email",
        "first@example.com",
        "--name",
        "First Admin",
    ]
    first = subprocess.run(
        command_line, env=environment, capture_output=True, text=True, timeout=30
    )
    assert first.returncode == 0, first.stdout + first.stderr
    repeated = subprocess.run(
        command_line, env=environment, capture_output=True, text=True, timeout=30
    )
    assert repeated.returncode == 0
    assert "unchanged" in repeated.stdout
    assert TEST_PASSWORD not in first.stdout + first.stderr

    token = client.post(
        "/api/auth/login",
        json={"email": "first@example.com", "password": TEST_PASSWORD},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).json()["roles"] == ["admin"]
    assert client.get("/api/users", headers=headers).status_code == 200
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "email": "workflow-coach@example.com",
            "full_name": "Workflow Coach",
            "password": TEST_PASSWORD,
            "roles": ["coach"],
        },
    )
    assert created.status_code == 201
    coach_token = client.post(
        "/api/auth/login",
        json={"email": "workflow-coach@example.com", "password": TEST_PASSWORD},
    ).json()["access_token"]
    coach_headers = {"Authorization": f"Bearer {coach_token}"}
    assert client.get("/api/auth/me", headers=coach_headers).json()["roles"] == [
        "coach"
    ]
    assert client.get("/api/users", headers=coach_headers).status_code == 403


def test_admin_script_does_not_promote_existing_user(
    settings: Settings, coach: User
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/create_admin.py"),
            "--email",
            coach.email,
            "--name",
            "Do not change",
        ],
        env={**os.environ, "DATABASE_URL": settings.database_url},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "No password, role or status was changed" in result.stdout
