"""Evaluation provenance and publication invariants, all synthetic fixtures."""

import json

import pytest
import test_evaluation_inputs as helpers
from pydantic import ValidationError

from app.core.config import Settings
from app.evaluation.configuration import pipeline_snapshot
from app.evaluation.inputs import (
    cleaned_diagnostics,
    load_landmarks,
    validate_calibration,
)
from app.evaluation.reporting import evaluate, publish
from app.evaluation.schemas import Clip, EvaluationConfig, InputError
from app.services.trajectory_artifacts import COLUMNS

evaluation_bundle = helpers.evaluation_bundle


def test_changed_input_during_publication_preserves_previous_run(evaluation_bundle):
    dataset, clips, predictions, hashes = helpers.load(evaluation_bundle)
    summary = evaluate(dataset, clips, predictions, EvaluationConfig(), {})
    output = evaluation_bundle[0] / "atomic"
    previous = publish(summary, output, hashes)
    original = (previous / "evaluation_summary.json").read_bytes()
    changed = evaluation_bundle[0] / "tracks.csv"
    changed.write_bytes(changed.read_bytes() + b"changed during evaluation")
    with pytest.raises(InputError, match="changed during evaluation"):
        publish(summary, output, hashes)
    assert list(output.iterdir()) == [previous]
    assert (previous / "evaluation_summary.json").read_bytes() == original


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_clip", "unknown_prediction", "mixed_provenance", "missing_weights"],
)
def test_manifest_rejects_untrustworthy_provenance(evaluation_bundle, mutation):
    _, dataset_path, predictions_path = evaluation_bundle
    dataset = json.loads(dataset_path.read_text())
    predictions = json.loads(predictions_path.read_text())
    if mutation == "duplicate_clip":
        dataset["clips"].append(dataset["clips"][0])
        dataset_path.write_text(json.dumps(dataset))
    elif mutation == "unknown_prediction":
        predictions["clips"][0]["clip_id"] = "missing"
    elif mutation == "mixed_provenance":
        predictions["source"] = "footlytics"
    else:
        predictions.pop("model_weights")
    predictions_path.write_text(json.dumps(predictions))
    with pytest.raises((InputError, ValidationError)):
        helpers.load(evaluation_bundle)


def test_reused_fitting_landmark_cannot_be_validation(evaluation_bundle):
    root, dataset_path, _ = evaluation_bundle
    path = root / "landmarks.csv"
    rows = [
        {
            "clip_id": "fixture",
            "landmark_id": "fit-1",
            "frame_number": 0,
            "image_x": 1,
            "image_y": 1,
            "pitch_x": 2,
            "pitch_y": 2,
            "role": "fit",
        }
    ]
    rows.append(rows[0] | {"landmark_id": "validation-1", "role": "validation"})
    helpers.write_csv(path, list(rows[0]), rows)
    values = json.loads(dataset_path.read_text())["clips"][0]
    values.update(
        landmarks=helpers.ref(path),
        calibration_frame_number=0,
        pitch_length_metres=40,
        pitch_width_metres=20,
    )
    with pytest.raises(InputError, match="invalid annotation"):
        load_landmarks(root, Clip.model_validate(values), EvaluationConfig())


def test_coordinate_artifact_requires_matching_saved_calibration(evaluation_bundle):
    _, clips, _, _ = helpers.load(evaluation_bundle)
    path = evaluation_bundle[0] / "calibration.json"
    clip = clips[0].clip.model_copy(
        update={"pitch_length_metres": 40, "pitch_width_metres": 20}
    )
    values = {
        "video_sha256": clip.video.sha256,
        "frame_number": 0,
        "pitch_length_metres": 40,
        "pitch_width_metres": 20,
        "matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    }
    path.write_text(json.dumps(values))
    validate_calibration(path, clip)
    values["video_sha256"] = "0" * 64
    path.write_text(json.dumps(values))
    with pytest.raises(InputError, match="calibration does not match"):
        validate_calibration(path, clip)


def test_cleaned_diagnostics_reject_nonfinite_values(evaluation_bundle):
    _, clips, _, _ = helpers.load(evaluation_bundle)
    path = evaluation_bundle[0] / "cleaned.csv"
    row = dict.fromkeys(COLUMNS, "0")
    row.update(
        frame_number="0",
        timestamp_seconds="0",
        track_id="10",
        x1="1",
        y1="1",
        x2="9",
        y2="15",
        confidence="0.9",
        clean_pitch_x="",
        clean_pitch_y="",
        usable="false",
        inside_pitch="true",
        is_interpolated="false",
    )
    helpers.write_csv(path, COLUMNS, [row])
    assert cleaned_diagnostics(path, clips[0], {0, 1, 2}, EvaluationConfig()) == (1, 0)
    row["raw_pitch_x"] = "nan"
    helpers.write_csv(path, COLUMNS, [row])
    with pytest.raises(InputError, match="invalid prediction"):
        cleaned_diagnostics(path, clips[0], {0, 1, 2}, EvaluationConfig())


def test_pipeline_snapshot_never_contains_credentials():
    settings = Settings(_env_file=None, environment="test", jwt_secret="not-for-export")
    snapshot = pipeline_snapshot(settings)
    assert snapshot["person_class_filter"] == "person"
    assert snapshot["ground_point"] == "bottom_centre"
    assert (
        not {"jwt_secret", "database_url", "redis_url", "storage_dir"} & snapshot.keys()
    )
