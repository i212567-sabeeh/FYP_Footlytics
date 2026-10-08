from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import PROJECT_ROOT, Settings


def test_paths_do_not_depend_on_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        _env_file=None,
        storage_dir="storage",
        database_url="sqlite:///./storage/footlytics.db",
    )

    assert settings.storage_dir == PROJECT_ROOT / "storage"
    assert (
        make_url(settings.database_url).database
        == (PROJECT_ROOT / "storage/footlytics.db").as_posix()
    )


def test_environment_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MAX_UPLOAD_SIZE=2048\nVITE_API_BASE_URL=/api\n")
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "4096")

    assert Settings(_env_file=env_file).max_upload_size == 4096


@pytest.mark.parametrize("value", [0, -1])
def test_upload_limit_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_upload_size=value)


@pytest.mark.parametrize("value", [0, 1.1])
def test_model_confidence_must_be_valid(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, yolo_confidence=value)


@pytest.mark.parametrize(
    "url", ["sqlite:///:memory:", "postgresql+psycopg://user:password@localhost/db"]
)
def test_other_database_urls_are_preserved(url: str) -> None:
    assert Settings(_env_file=None, database_url=url).database_url == url
