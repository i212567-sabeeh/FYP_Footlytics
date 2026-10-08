"""Generated storage names, bounded path resolution and atomic publication."""

import logging
import os
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from app.core.config import Settings
from app.services.domain_common import DomainError

logger = logging.getLogger(__name__)
ALLOWED_VIDEO_SUFFIXES = frozenset({".mp4", ".mov"})


class StorageService:
    def __init__(self, settings: Settings):
        self.root = settings.storage_dir.resolve()

    def resolve(self, relative_path: str) -> Path:
        """Treat stored paths as untrusted, including Windows paths on Linux."""
        if (
            not relative_path
            or "\\" in relative_path
            or ":" in relative_path
            or "\x00" in relative_path
            or PurePosixPath(relative_path).is_absolute()
            or PureWindowsPath(relative_path).is_absolute()
            or any(part in {".", ".."} for part in relative_path.split("/"))
        ):
            raise DomainError(500, "The stored video location is invalid.")
        return self._checked(self.root / relative_path)

    def _checked(self, path: Path) -> Path:
        try:
            if not path.is_absolute() or ".." in path.parts:
                raise DomainError(500, "The stored video location is invalid.")
            if path == self.root or not path.is_relative_to(self.root):
                raise DomainError(500, "The stored video location is invalid.")
            resolved = path.resolve()
            if resolved == self.root or not resolved.is_relative_to(self.root):
                raise DomainError(500, "The stored video location is invalid.")
            # Reject redirected components even when a link currently stays inside
            # storage. Storage directories are application-owned, not user inputs.
            candidate = path
            while candidate != self.root:
                if candidate.is_symlink() or candidate.is_junction():
                    raise DomainError(500, "The stored video location is invalid.")
                candidate = candidate.parent
            return resolved
        except (OSError, ValueError, RuntimeError):
            raise DomainError(500, "The stored video location is invalid.") from None

    @staticmethod
    def _suffix(suffix: str) -> str:
        suffix = suffix.lower()
        if suffix not in ALLOWED_VIDEO_SUFFIXES:
            raise DomainError(422, "Only MP4 and MOV video files are supported.")
        return suffix

    def _match_directory(self, match_id: int) -> Path:
        if isinstance(match_id, bool) or not isinstance(match_id, int) or match_id <= 0:
            raise DomainError(500, "The stored video location is invalid.")
        return self.resolve(f"raw/matches/{match_id}")

    def create_temporary(self, match_id: int, suffix: str) -> Path:
        suffix = self._suffix(suffix)
        directory = self._checked(self._match_directory(match_id) / ".temporary")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(suffix=suffix, dir=directory)
            os.close(descriptor)
            return self._checked(Path(name))
        except OSError:
            logger.exception("Could not create temporary video storage")
            raise DomainError(
                500, "Video storage is unavailable. Try again later."
            ) from None

    def finalize(self, temp_path: Path, match_id: int, suffix: str) -> tuple[str, str]:
        suffix = self._suffix(suffix)
        directory = self._match_directory(match_id)
        temporary = self._checked(temp_path)
        if temporary.parent != directory / ".temporary" or not temporary.is_file():
            raise DomainError(500, "The temporary video could not be finalized.")
        destination: Path | None = None
        try:
            # Exclusive reservation prevents even a UUID collision from replacing
            # another artifact. Only the publishing service knows this name yet.
            for _ in range(10):
                candidate = self._checked(directory / f"{uuid4().hex}{suffix}")
                try:
                    with candidate.open("xb"):
                        pass
                except FileExistsError:
                    continue
                destination = candidate
                break
            if destination is None:
                raise OSError("Could not reserve a unique storage filename")
            os.replace(temporary, destination)
        except OSError:
            if destination is not None:
                self.delete(destination.relative_to(self.root).as_posix())
            logger.exception("Could not finalize uploaded video")
            raise DomainError(
                500, "The video could not be saved. Try again later."
            ) from None
        return destination.name, destination.relative_to(self.root).as_posix()

    def delete(self, relative_path: str) -> None:
        path = self.resolve(relative_path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove stored video")
            raise DomainError(500, "The stored video could not be removed.") from None

    def discard_temporary(self, path: Path) -> None:
        checked = self._checked(path)
        relative = checked.relative_to(self.root)
        if (
            len(relative.parts) != 5
            or relative.parts[:2] != ("raw", "matches")
            or not relative.parts[2].isdigit()
            or relative.parts[3] != ".temporary"
        ):
            raise DomainError(500, "The temporary video location is invalid.")
        self.delete(relative.as_posix())
