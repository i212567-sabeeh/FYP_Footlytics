from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from alembic import command
from app.auth.roles import RoleName
from app.auth.tokens import create_access_token
from app.core.config import PROJECT_ROOT, Settings
from app.database.session import create_database_engine, create_session_factory
from app.main import create_app
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user_service import create_user

# Explicitly synthetic credentials, used only with disposable test databases.
TEST_SECRET = "test-only-jwt-signing-secret-do-not-use-for-real-accounts-123456789"
TEST_PASSWORD = "Test-password-123"


def migration_config(connection=None) -> Config:
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        jwt_secret=SecretStr(TEST_SECRET),
        database_url=f"sqlite:///{(tmp_path / 'auth-test.db').as_posix()}",
        storage_dir=tmp_path / "storage",
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    database_engine = create_database_engine(settings.database_url)
    with database_engine.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    yield database_engine
    database_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as database_session:
        yield database_session


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def admin(session: Session) -> User:
    user = create_user(
        session,
        UserCreate(
            email="admin@example.com",
            full_name="Test Admin",
            password=TEST_PASSWORD,
            roles=[RoleName.ADMIN],
        ),
    )
    # End refresh's read transaction before the API uses a separate connection.
    session.commit()
    return user


@pytest.fixture
def coach(session: Session) -> User:
    user = create_user(
        session,
        UserCreate(
            email="coach@example.com",
            full_name="Test Coach",
            password=TEST_PASSWORD,
            roles=[RoleName.COACH, RoleName.ANALYST],
        ),
    )
    session.commit()
    return user


@pytest.fixture
def admin_headers(admin: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(admin.id, settings)}"}


@pytest.fixture
def coach_headers(coach: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(coach.id, settings)}"}
