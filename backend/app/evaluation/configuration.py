"""Only CV settings belong in a reproducibility snapshot; never include secrets."""

import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from app.evaluation.schemas import InputError

PREFIXES = ("yolo_", "track_", "team_", "trajectory_")
EXTRA_FIELDS = ("device", "detection_frame_stride", "detection_roi_enabled")


def pipeline_snapshot(settings: Settings) -> dict:
    return {
        name: getattr(settings, name)
        for name in Settings.model_fields
        if (name.startswith(PREFIXES) or name in EXTRA_FIELDS)
        and not name.endswith("timeout_seconds")
    } | {"person_class_filter": "person", "ground_point": "bottom_centre"}


def digest_json(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def evaluator_digest() -> str:
    """Fingerprint this evaluator even in a checkout without Git metadata."""
    return digest_json(
        {
            path.relative_to(Path(__file__).parent).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(Path(__file__).parent.rglob("*.py"))
        }
    )


def validate_pipeline_snapshot(value: dict) -> None:
    defaults = pipeline_snapshot(Settings(_env_file=None, environment="test"))
    if set(value) != set(defaults):
        raise InputError(
            "Prediction configuration must contain the complete CV snapshot"
        )
    if (
        value["person_class_filter"] != "person"
        or value["ground_point"] != "bottom_centre"
    ):
        raise InputError(
            "Predictions must use the existing person/bottom-centre pipeline"
        )
    # Settings provides the production bounds, without reading local credentials.
    Settings(
        _env_file=None,
        environment="test",
        **{key: item for key, item in value.items() if key in Settings.model_fields},
    )
