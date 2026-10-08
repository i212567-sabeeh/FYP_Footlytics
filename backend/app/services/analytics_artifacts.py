"""Publish a complete, immutable CSV bundle with one same-filesystem rename."""

import csv
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.player_analytics import (
    HeatmapCell,
    MovementInterval,
    SprintEvent,
    TrackAnalytics,
)
from app.services.storage_service import StorageService
from app.services.tracking_inputs import file_version

MODELS = {
    "players": TrackAnalytics,
    "intervals": MovementInterval,
    "sprints": SprintEvent,
    "heatmaps": HeatmapCell,
}


class AnalyticsArtifacts:
    models = MODELS
    prefix = "analytics"

    def __init__(
        self,
        settings: Settings,
        match_id: int,
        video_id: int,
        job_id: int,
        attempt: int,
    ):
        self.storage = StorageService(settings)
        self.relative = (
            f"{self.prefix}/matches/{match_id}/videos/{video_id}/jobs/{job_id}/"
            f"attempt-{attempt}-{uuid4().hex}"
        )
        self.path = self.storage.resolve(self.relative)
        self.temporary = self.storage.resolve(self.relative + ".partial")
        self.files = {}
        self.writers = {}
        self.published = self.kept = False

    def __enter__(self):
        self.temporary.mkdir(parents=True, exist_ok=False)
        try:
            for name, model in self.models.items():
                stream = (self.temporary / f"{name}.csv").open(
                    "x", newline="", encoding="utf-8"
                )
                self.files[name] = stream
                writer = csv.DictWriter(stream, fieldnames=tuple(model.model_fields))
                self.writers[name] = writer
                writer.writeheader()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def write(self, name: str, row: BaseModel) -> None:
        # Revalidate calculated values before persisting (no NaN/Inf/null tricks).
        data = self.models[name].model_validate(row.model_dump()).model_dump()
        self.writers[name].writerow(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in data.items()
            }
        )

    def publish(self) -> str:
        for stream in self.files.values():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        temporary = self.storage.resolve(self.relative + ".partial")
        destination = self.storage.resolve(self.relative)
        if destination.exists():
            raise FileExistsError("Analytics attempt already exists")
        os.rename(temporary, destination)
        self.published = True
        return self.relative

    def versions(self) -> dict:
        return {
            name: file_version(self.storage.resolve(f"{self.relative}/{name}.csv"))
            for name in self.models
        }

    def keep(self) -> None:
        self.kept = True

    def __exit__(self, *_args):
        for stream in self.files.values():
            stream.close()
        if not self.kept:
            # Only remove known files belonging to this unique attempt, never a
            # recursive delete or a previous successful job's published bundle.
            relative = self.relative if self.published else self.relative + ".partial"
            directory = self.storage.resolve(relative)
            for name in self.models:
                self.storage.resolve(f"{relative}/{name}.csv").unlink(missing_ok=True)
            if directory.exists():
                directory.rmdir()


def read_rows(path: Path, name: str, models: dict = MODELS):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != tuple(models[name].model_fields):
            raise ValueError("Invalid analytics columns")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid analytics row")
            yield models[name].model_validate(
                {key: value if value != "" else None for key, value in row.items()}
            )
