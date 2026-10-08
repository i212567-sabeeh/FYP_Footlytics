"""Attempt-specific PDF publication; the database selects the current snapshot."""

import os
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from app.core.config import Settings
from app.services.storage_service import StorageService


def validate_pdf(path: Path) -> tuple[int, int]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        if size < 32 or stream.read(5) != b"%PDF-":
            raise ValueError("Invalid report PDF signature")
        stream.seek(-min(size, 1024), os.SEEK_END)
        if not stream.read().rstrip().endswith(b"%%EOF"):
            raise ValueError("Truncated report PDF")
        stream.seek(0)
        reader = PdfReader(stream, strict=True)
        count = len(reader.pages)
        if reader.is_encrypted or count < 1:
            raise ValueError("Report PDF has no readable pages")
        for page in reader.pages:
            if float(page.mediabox.width) <= 0 or float(page.mediabox.height) <= 0:
                raise ValueError("Invalid report page")
            # Resolve/decode the content streams before allowing publication.
            content = page.get_contents()
            if content is not None:
                content.get_data()
    return count, size


class ReportArtifact:
    def __init__(
        self,
        settings: Settings,
        match_id: int,
        video_id: int,
        job_id: int,
        attempt: int,
    ):
        if min(match_id, video_id, job_id) < 1 or attempt < 0:
            raise ValueError("Invalid report identifiers")
        self.storage = StorageService(settings)
        self.relative = (
            f"reports/matches/{match_id}/videos/{video_id}/jobs/{job_id}/"
            f"attempt-{attempt}-{uuid4().hex}.pdf"
        )
        self.path = self.storage.resolve(self.relative)
        self.temporary = self.storage.resolve(self.relative + ".partial")
        self.published = False
        self.kept = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.temporary.open("xb").close()
        return self

    def publish(self) -> str:
        temporary = self.storage.resolve(self.relative + ".partial")
        destination = self.storage.resolve(self.relative)
        if destination.exists():
            raise FileExistsError("Report attempt already exists")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.rename(temporary, destination)
        self.published = True
        return self.relative

    def keep(self) -> None:
        self.kept = True

    def __exit__(self, *_args):
        if not self.kept:
            self.storage.delete(self.relative + ".partial")
            if self.published:
                self.storage.delete(self.relative)
