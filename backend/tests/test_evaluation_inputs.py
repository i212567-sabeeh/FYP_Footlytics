"""Strict input/provenance checks using deliberately synthetic tiny fixtures."""

import csv
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.evaluation.configuration import digest_json, pipeline_snapshot
from app.evaluation.inputs import GT_COLUMNS, load_dataset, sha256
from app.evaluation.run import main
from app.evaluation.schemas import EvaluationConfig, InputError


def write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def ref(path: Path) -> dict:
    return {"path": path.name, "sha256": sha256(path)}


@pytest.fixture
def evaluation_bundle(tmp_path):
    weights = tmp_path / "synthetic-weights.txt"
    weights.write_text("SYNTHETIC FIXTURE ONLY; not actual YOLO weights")
    video = tmp_path / "synthetic.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 24))
    assert writer.isOpened()
    for _ in range(3):
        writer.write(np.zeros((24, 32, 3), np.uint8))
    writer.release()
    frames = [
        {
            "clip_id": "fixture",
            "frame_number": i,
            "timestamp_seconds": i / 10,
            "tracking_evaluable": "true",
        }
        for i in range(3)
    ]
    write_csv(tmp_path / "frames.csv", list(frames[0]), frames)
    boxes = [
        {
            "clip_id": "fixture",
            "frame_number": i,
            "timestamp_seconds": i / 10,
            "ground_truth_track_id": "human-1",
            "team_label": "team_a",
            "ignored": "false",
            "x1": 1,
            "y1": 1,
            "x2": 9,
            "y2": 15,
            "pitch_x": "",
            "pitch_y": "",
        }
        for i in range(3)
    ]
    write_csv(tmp_path / "boxes.csv", list(boxes[0]), boxes)
    predictions = [
        {
            "frame_number": i,
            "timestamp_seconds": i / 10,
            "x1": 1,
            "y1": 1,
            "x2": 9,
            "y2": 15,
            "confidence": 0.9,
            "track_id": 10,
        }
        for i in range(3)
    ]
    write_csv(tmp_path / "detections.csv", list(predictions[0]), predictions)
    write_csv(tmp_path / "tracks.csv", list(predictions[0]), predictions)
    write_csv(
        tmp_path / "teams.csv",
        [
            "track_id",
            "automatic_team",
            "automatic_confidence",
            "manual_team",
            "effective_team",
        ],
        [
            {
                "track_id": 10,
                "automatic_team": "unknown",
                "automatic_confidence": 0.1,
                "manual_team": "team_a",
                "effective_team": "team_a",
            }
        ],
    )
    dataset = {
        "schema_version": 1,
        "description": "SYNTHETIC TEST — NOT REAL MODEL ACCURACY",
        "provenance": "synthetic",
        "annotation_author": "test fixture",
        "annotation_notes": "Analytic boxes only",
        "independent_ground_truth": False,
        "clips": [
            {
                "clip_id": "fixture",
                "video": ref(video),
                "frames": ref(tmp_path / "frames.csv"),
                "annotations": ref(tmp_path / "boxes.csv"),
                "fps": 10,
                "frame_count": 3,
                "width": 32,
                "height": 24,
                "duration_seconds": 0.3,
                "football_format": "5v5",
                "conditions": "Synthetic black frames",
                "team_mapping": {"team_a": "team_a", "team_b": "team_b"},
                "team_mapping_basis": "Fixed synthetic mapping",
            }
        ],
    }
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    config = pipeline_snapshot(Settings(_env_file=None, environment="test"))
    manifest = {
        "schema_version": 1,
        "source": "synthetic",
        "generated_at": "2026-10-05T00:00:00Z",
        "dataset_sha256": sha256(dataset_path),
        "pipeline_config": config,
        "software_versions": {"fixture": "1"},
        "model_weights": ref(weights),
        "source_revision": "synthetic test",
        "clips": [
            {
                "clip_id": "fixture",
                "video_sha256": sha256(video),
                "pipeline_config_sha256": digest_json(config),
                "processed_frames": [0, 1, 2],
                "detections": ref(tmp_path / "detections.csv"),
                "tracks": ref(tmp_path / "tracks.csv"),
                "automatic_teams": ref(tmp_path / "teams.csv"),
            }
        ],
    }
    pred_path = tmp_path / "predictions.json"
    pred_path.write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, dataset_path, pred_path


def mutate_csv(bundle, name, change, *, prediction=False):
    root, dataset_path, prediction_path = bundle
    path = root / name
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        columns, rows = reader.fieldnames, list(reader)
    change(rows)
    write_csv(path, columns, rows)
    dataset = json.loads(dataset_path.read_text())
    manifest = json.loads(prediction_path.read_text())
    if prediction:
        key = {
            "tracks.csv": "tracks",
            "detections.csv": "detections",
            "teams.csv": "automatic_teams",
        }[name]
        manifest["clips"][0][key] = ref(path)
    else:
        key = "annotations" if name == "boxes.csv" else "frames"
        dataset["clips"][0][key] = ref(path)
        dataset_path.write_text(json.dumps(dataset))
        manifest["dataset_sha256"] = sha256(dataset_path)
    prediction_path.write_text(json.dumps(manifest))


def load(bundle, **kwargs):
    return load_dataset(
        bundle[1], bundle[2], EvaluationConfig(), allow_synthetic=True, **kwargs
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda rows: rows[0].update(x2="0"),
        lambda rows: rows[0].update(x1="nan"),
        lambda rows: rows[0].update(y2="inf"),
        lambda rows: rows[0].update(frame_number="-1"),
        lambda rows: rows[0].update(team_label="red"),
        lambda rows: rows[0].update(clip_id="unknown"),
        lambda rows: rows.append(dict(rows[0])),
        lambda rows: rows[0].update(pitch_x="3", pitch_y=""),
        lambda rows: rows[0].update(pitch_x="3", pitch_y="4"),
        lambda rows: rows[0].update(ground_truth_track_id=""),
    ],
)
def test_invalid_annotations_are_rejected(evaluation_bundle, change):
    mutate_csv(evaluation_bundle, "boxes.csv", change)
    with pytest.raises(InputError) as failure:
        load(evaluation_bundle)
    assert failure.value.issues and failure.value.issues[0]["kind"] == "annotation"


@pytest.mark.parametrize(
    "change",
    [
        lambda rows: rows[0].update(x1="nan"),
        lambda rows: rows[0].update(x2="1"),
        lambda rows: rows[0].update(confidence="inf"),
        lambda rows: rows[0].update(frame_number="999"),
        lambda rows: rows[0].update(track_id="0"),
        lambda rows: rows.append(dict(rows[0])),
    ],
)
def test_invalid_prediction_rows_are_reported_separately(evaluation_bundle, change):
    mutate_csv(evaluation_bundle, "tracks.csv", change, prediction=True)
    with pytest.raises(InputError) as failure:
        load(evaluation_bundle)
    assert failure.value.issues and failure.value.issues[0]["kind"] == "prediction"


def test_manual_team_overrides_cannot_inflate_accuracy(evaluation_bundle):
    from app.evaluation.teams import evaluate_teams

    _, clips, _, _ = load(evaluation_bundle)
    result = evaluate_teams(clips)
    assert result["accuracy"] == result["coverage"] == 0
    assert result["unknown_rate"] == 1
    assert result["accuracy_among_classified"] is None


@pytest.mark.parametrize("filename", ["synthetic.avi", "tracks.csv", "boxes.csv"])
def test_changed_video_or_artifact_is_rejected(evaluation_bundle, filename):
    path = evaluation_bundle[0] / filename
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(InputError, match="changed"):
        load(evaluation_bundle)


def test_changed_configuration_and_missing_empty_frame_provenance(evaluation_bundle):
    path = evaluation_bundle[2]
    original = json.loads(path.read_text())
    changed = json.loads(path.read_text())
    changed["pipeline_config"]["track_buffer"] += 1
    path.write_text(json.dumps(changed))
    with pytest.raises(InputError, match="Stale"):
        load(evaluation_bundle)
    original["clips"][0]["processed_frames"] = [0, 1]
    path.write_text(json.dumps(original))
    with pytest.raises(InputError, match="Every reviewed frame"):
        load(evaluation_bundle)


def test_synthetic_requires_explicit_opt_in(evaluation_bundle):
    with pytest.raises(InputError, match="Synthetic data requires"):
        load_dataset(evaluation_bundle[1], evaluation_bundle[2], EvaluationConfig())


def test_synthetic_cli_writes_all_outputs_without_model_loading(
    evaluation_bundle, monkeypatch
):
    import app.cv.detector

    monkeypatch.setattr(
        app.cv.detector,
        "YoloPlayerDetector",
        lambda *_: pytest.fail("Evaluator must not rerun YOLO"),
    )
    root, dataset, predictions = evaluation_bundle
    output = root / "results"
    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--predictions",
                str(predictions),
                "--output",
                str(output),
                "--allow-synthetic",
            ]
        )
        == 0
    )
    folder = next(output.iterdir())
    summary = json.loads((folder / "evaluation_summary.json").read_text())
    assert summary["status"] == "synthetic_evaluator_test"
    assert summary["notice"] == "SYNTHETIC TEST — NOT REAL MODEL ACCURACY"
    assert summary["detection"]["tp"] == 3
    assert summary["tracking"]["idf1"] == 1
    assert summary["team_classification"]["accuracy"] == 0
    assert summary["coordinates"]["player_coordinates"]["mean"] is None
    assert summary["runtime"][0]["seconds"] is None
    for name in (
        "evaluation_report.md",
        "configuration.json",
        "detection_metrics.csv",
        "tracking_metrics.csv",
        "team_classification_metrics.csv",
        "coordinate_metrics.csv",
        "runtime_metrics.csv",
        "confusion_matrix.csv",
        "invalid_rows.csv",
    ):
        assert (folder / name).is_file()


def test_invalid_cli_saves_diagnostics_without_accuracy(evaluation_bundle):
    mutate_csv(
        evaluation_bundle,
        "tracks.csv",
        lambda rows: rows[0].update(x1="nan"),
        prediction=True,
    )
    root, dataset, predictions = evaluation_bundle
    output = root / "invalid-results"
    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--predictions",
                str(predictions),
                "--output",
                str(output),
                "--allow-synthetic",
            ]
        )
        == 2
    )
    folder = next(output.iterdir())
    summary = json.loads((folder / "evaluation_summary.json").read_text())
    assert (
        summary["status"] == "invalid_inputs" and not summary["detection"]["available"]
    )
    assert "prediction" in (folder / "invalid_rows.csv").read_text()


def test_inventory_has_no_fabricated_accuracy(tmp_path):
    assert (
        main(
            [
                "--inventory",
                "--clips",
                str(tmp_path / "clips"),
                "--annotations",
                str(tmp_path / "annotations"),
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 0
    )
    folder = next((tmp_path / "output").iterdir())
    summary = json.loads((folder / "evaluation_summary.json").read_text())
    assert summary["status"] == "real_annotation_pending"
    assert summary["clip_count"] == summary["annotated_frames"] == 0
    assert (
        not summary["detection"]["available"] and not summary["tracking"]["available"]
    )


def test_required_columns_rejected(evaluation_bundle):
    assert "ground_truth_track_id" in GT_COLUMNS
    path = evaluation_bundle[0] / "boxes.csv"
    write_csv(path, ["clip_id"], [{"clip_id": "fixture"}])
    dataset = json.loads(evaluation_bundle[1].read_text())
    dataset["clips"][0]["annotations"] = ref(path)
    evaluation_bundle[1].write_text(json.dumps(dataset))
    with pytest.raises(InputError, match="required columns"):
        load_dataset(
            evaluation_bundle[1], None, EvaluationConfig(), allow_synthetic=True
        )
