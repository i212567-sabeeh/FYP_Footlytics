from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from app.core.config import Settings
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService


@pytest.fixture
def storage(tmp_path: Path) -> StorageService:
    return StorageService(Settings(_env_file=None, storage_dir=tmp_path / "storage"))


def test_finalize_publishes_generated_path_and_removes_temporary(storage):
    first = storage.create_temporary(23, ".mp4")
    first.write_bytes(b"test-only synthetic bytes")
    filename, relative = storage.finalize(first, 23, ".mp4")
    assert filename.endswith(".mp4")
    assert len(filename.removesuffix(".mp4")) == 32
    assert relative == f"raw/matches/23/{filename}"
    assert not first.exists()
    assert storage.resolve(relative).read_bytes() == b"test-only synthetic bytes"

    second = storage.create_temporary(23, ".MOV")
    second.write_bytes(b"another test-only fixture")
    second_name, _ = storage.finalize(second, 23, ".mov")
    assert second_name != filename
    assert storage.resolve(relative).read_bytes() == b"test-only synthetic bytes"


def test_uuid_collision_does_not_overwrite_existing_file(storage):
    first = storage.create_temporary(1, ".mp4")
    first.write_bytes(b"old")
    same_uuid = UUID(int=1)
    with patch("app.services.storage_service.uuid4", return_value=same_uuid):
        _, old_path = storage.finalize(first, 1, ".mp4")
    second = storage.create_temporary(1, ".mp4")
    second.write_bytes(b"new")
    with patch(
        "app.services.storage_service.uuid4", side_effect=[same_uuid, UUID(int=2)]
    ):
        _, new_path = storage.finalize(second, 1, ".mp4")
    assert storage.resolve(old_path).read_bytes() == b"old"
    assert storage.resolve(new_path).read_bytes() == b"new"


@pytest.mark.parametrize(
    "relative",
    [
        "../outside.mp4",
        "raw/../../outside.mp4",
        "/absolute.mp4",
        "C:/outside.mp4",
        "C:outside.mp4",
        "\\\\server\\share\\outside.mp4",
        "raw\\..\\outside.mp4",
        "raw/matches/1/video.mp4:stream",
        "raw/\x00video.mp4",
        "",
        ".",
        "raw/./video.mp4",
    ],
)
def test_unsafe_stored_paths_are_rejected(storage, relative):
    with pytest.raises(DomainError) as error:
        storage.resolve(relative)
    assert error.value.status_code == 500
    assert relative not in error.value.detail or relative in {"", "."}


def test_finalization_cannot_move_another_match_temporary_file(storage):
    first = storage.create_temporary(1, ".mp4")
    with pytest.raises(DomainError):
        storage.finalize(first, 2, ".mp4")
    assert first.exists()


def test_cleanup_is_idempotent_and_cannot_delete_final_file(storage):
    temporary = storage.create_temporary(1, ".mp4")
    storage.discard_temporary(temporary)
    storage.discard_temporary(temporary)
    assert not temporary.exists()
    temporary = storage.create_temporary(1, ".mp4")
    _, relative = storage.finalize(temporary, 1, ".mp4")
    with pytest.raises(DomainError):
        storage.discard_temporary(storage.resolve(relative))
    storage.delete(relative)
    storage.delete(relative)


def test_cleanup_rejects_relative_or_outside_paths_without_touching_them(
    storage, tmp_path
):
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"protected test fixture")
    for unsafe in (outside, Path("raw/matches/1/.temporary/file.mp4")):
        with pytest.raises(DomainError):
            storage.discard_temporary(unsafe)
    assert outside.read_bytes() == b"protected test fixture"


@pytest.mark.parametrize("match_id", [0, -1, "../outside", True])
def test_invalid_match_storage_identifier(storage, match_id):
    with pytest.raises(DomainError):
        storage.create_temporary(match_id, ".mp4")


@pytest.mark.parametrize("suffix", [".exe", "/evil.mp4", ".mp4/../../escape"])
def test_invalid_storage_suffix(storage, suffix):
    with pytest.raises(DomainError) as error:
        storage.create_temporary(1, suffix)
    assert error.value.status_code == 422


def test_symlink_components_are_rejected_before_read_or_delete(storage, monkeypatch):
    safe = storage.root / "raw" / "matches" / "1" / "video.mp4"
    redirected = storage.root / "raw"
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == redirected or original(path)
    )
    with pytest.raises(DomainError):
        storage.resolve(safe.relative_to(storage.root).as_posix())


def test_disk_failure_keeps_source_and_cleans_final_reservation(storage):
    temporary = storage.create_temporary(1, ".mp4")
    temporary.write_bytes(b"test-only bytes")
    with patch("app.services.storage_service.os.replace", side_effect=OSError("disk")):
        with pytest.raises(DomainError) as error:
            storage.finalize(temporary, 1, ".mp4")
    assert error.value.status_code == 500
    assert temporary.exists()
    assert list(temporary.parent.parent.glob("*.mp4")) == []
    storage.discard_temporary(temporary)


def test_temporary_creation_disk_failure_has_safe_error(storage):
    with patch("app.services.storage_service.tempfile.mkstemp", side_effect=OSError()):
        with pytest.raises(DomainError) as error:
            storage.create_temporary(1, ".mp4")
    assert error.value.status_code == 500
    assert str(storage.root) not in error.value.detail
