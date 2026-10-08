"""Portable JSON/CSV/Markdown evidence with unavailable values kept explicit."""

import csv
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.evaluation.configuration import evaluator_digest
from app.evaluation.coordinates import evaluate_coordinates
from app.evaluation.detection import evaluate_detection
from app.evaluation.inputs import recheck
from app.evaluation.schemas import ClipData, Dataset, EvaluationConfig, Predictions
from app.evaluation.teams import evaluate_teams
from app.evaluation.tracking import evaluate_tracking

STAGES = ("detection", "tracking", "team_classification", "coordinate_mapping")


def coverage(clip: ClipData) -> dict:
    players = [r for r in clip.annotations if not r.ignored and r.team != "official"]
    return {
        "clip_id": clip.clip.clip_id,
        "duration_seconds": clip.clip.duration_seconds,
        "width": clip.clip.width,
        "height": clip.clip.height,
        "fps": clip.clip.fps,
        "football_format": clip.clip.football_format,
        "conditions": clip.clip.conditions,
        "annotated_frames": len(clip.frames),
        "ground_truth_boxes": len(players),
        "ground_truth_tracks": len({r.track_id for r in players if r.track_id}),
        "team_labelled_tracks": len(
            {
                r.track_id
                for r in players
                if r.track_id and r.team in {"team_a", "team_b"}
            }
        ),
        "ignored_boxes": len(clip.annotations) - len(players),
        "fit_landmarks": sum(p.role == "fit" for p in clip.landmarks),
        "validation_landmarks": sum(p.role == "validation" for p in clip.landmarks),
        "independent_player_positions": sum(r.pitch is not None for r in players),
    }


def diagnostics(clip: ClipData) -> dict:
    labels = list((clip.automatic_teams or {}).values())
    return {
        "processed_frames": len(clip.prediction.processed_frames)
        if clip.prediction
        else None,
        "detection_rows": len(clip.detections) if clip.detections is not None else None,
        "unique_predicted_tracks": len({r.track_id for r in clip.tracks})
        if clip.tracks is not None
        else None,
        "classified_tracks": sum(label != "unknown" for label in labels)
        if clip.automatic_teams is not None
        else None,
        "unknown_prediction_rate": sum(label == "unknown" for label in labels)
        / len(labels)
        if labels
        else None,
        "mapped_coordinate_rows": len(clip.coordinates)
        if clip.coordinates is not None
        else None,
        "cleaned_rows": clip.cleaned_rows,
        "usable_cleaned_rows": clip.usable_cleaned_rows,
        "interpretation": "Processing diagnostics, not accuracy metrics",
    }


def runtime_rows(clips: list[ClipData]) -> list[dict]:
    rows = []
    for clip in clips:
        measurements = (
            {r.stage: r for r in clip.prediction.runtime} if clip.prediction else {}
        )
        for stage in STAGES:
            measurement = measurements.get(stage)
            row = {
                "clip_id": clip.clip.clip_id,
                "stage": stage,
                "available": measurement is not None,
                "seconds": None,
                "frames": None,
                "frames_per_second": None,
                "device": None,
                "setup_included": None,
                "hardware": None,
                "measurement_method": None,
                "reason": "No measured stage timing in the prediction provenance",
            }
            if measurement:
                row.update(
                    measurement.model_dump(),
                    frames_per_second=measurement.frames / measurement.seconds,
                    reason=None,
                )
            rows.append(row)
    return rows


def evaluate(
    dataset: Dataset,
    clips: list[ClipData],
    predictions: Predictions | None,
    config: EvaluationConfig,
    environment: dict,
) -> dict:
    tracking, by_clip = evaluate_tracking(clips, config.tracking_iou)
    per_clip = {}
    for clip in clips:
        identifier = clip.clip.clip_id
        per_clip[identifier] = {
            "coverage": coverage(clip),
            "diagnostics": diagnostics(clip),
            "detection": evaluate_detection([clip], config.detection_iou),
            "tracking": by_clip.get(identifier),
            "teams": evaluate_teams([clip], config.association_iou),
            "coordinates": evaluate_coordinates(
                [clip], config.association_iou, config.p95_min_observations
            ),
        }
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "status": "synthetic_evaluator_test"
        if dataset.provenance == "synthetic"
        else ("evaluated" if clips else "real_annotation_pending"),
        "provenance": dataset.provenance,
        "notice": "SYNTHETIC TEST — NOT REAL MODEL ACCURACY"
        if dataset.provenance == "synthetic"
        else (
            "Accuracy requires independent human annotations; "
            "missing metrics remain unavailable"
        ),
        "dataset": dataset.model_dump(mode="json"),
        "clip_count": len(clips),
        "annotated_frames": sum(len(c.frames) for c in clips),
        "environment": environment,
        "metric_configuration": config.model_dump(),
        "evaluator_source_sha256": evaluator_digest(),
        "prediction_provenance": predictions.model_dump(mode="json")
        if predictions
        else None,
        "detection": evaluate_detection(clips, config.detection_iou),
        "tracking": tracking,
        "team_classification": evaluate_teams(clips, config.association_iou),
        "coordinates": evaluate_coordinates(
            clips, config.association_iou, config.p95_min_observations
        ),
        "per_clip": per_clip,
        "runtime": runtime_rows(clips),
        "runtime_reason": None
        if any(c.prediction and c.prediction.runtime for c in clips)
        else (
            "No representative clip stage timings available; "
            "scorer duration is not inference throughput"
        ),
        "limitations": [
            "Local player-only protocol with documented ignore regions; "
            "not an official MOTChallenge submission.",
            "MOTP is mean IoU distance (1-IoU); lower is better. "
            "IDs are scoped to each clip.",
            "AP50 is all-points AP over saved confidence-filtered predictions, "
            "not COCO mAP50:95.",
            "Classification uses spatial GT/track association and automatic labels "
            "only; unmatched eligible GT tracks count as Unknown.",
            "GT unknown/official labels are excluded from two-team "
            "classification denominators.",
            "Coordinate errors cover matched independent positions; "
            "coverage and misses must accompany them.",
            "Held-out landmarks must not participate in fitting. "
            "A single camera pose does not validate camera motion.",
            "No trajectory accuracy is claimed without independent positions; "
            "synthetic behavior tests remain separate.",
            "Small or sampled clips may not represent every camera, "
            "occlusion, jersey or football format.",
        ],
    }


def write_csv(path: Path, rows: list[dict], default_columns: list[str]) -> None:
    columns = list(dict.fromkeys(key for row in rows for key in row)) or default_columns
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            clean = {}
            for key, value in row.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True, allow_nan=False)
                if isinstance(value, str) and value.lstrip().startswith(
                    ("=", "+", "-", "@")
                ):
                    value = "'" + value
                clean[key] = value
            writer.writerow(clean)


def markdown(summary: dict) -> str:
    lines = [
        "# FOOTLYTICS computer-vision evaluation",
        "",
        summary["notice"],
        "",
        f"Status: **{summary['status']}**. Clips: {summary['clip_count']}; "
        f"reviewed frames: {summary['annotated_frames']}.",
        "",
        "## Dataset",
        "",
        summary["dataset"]["description"],
        "",
        "Annotation coverage and conditions are recorded per clip "
        "in evaluation_summary.json.",
        "",
        "## Methodology",
        "",
        "Detection uses threshold-gated one-to-one assignment. Tracking uses "
        "motmetrics CLEAR MOT and Identity metrics. Team labels are aligned using "
        "spatial matches, never by maximizing classification accuracy. "
        "Errors use independent pitch positions in metres.",
        "",
        "## Aggregate results",
        "",
    ]
    for family in ("detection", "tracking", "team_classification", "coordinates"):
        lines.extend(
            [
                f"### {family}",
                "",
                "```json",
                json.dumps(summary[family], indent=2, allow_nan=False),
                "```",
                "",
            ]
        )
    if "external_dataset" in summary:
        lines.extend(
            [
                "## External dataset and validation gates",
                "",
                "```json",
                json.dumps(summary["external_dataset"], indent=2, allow_nan=False),
                "```",
                "",
            ]
        )
    lines.extend(["## Per-clip results", ""])
    for identifier, clip in summary["per_clip"].items():
        lines.extend(
            [
                f"### {identifier}",
                "",
                "```json",
                json.dumps(clip, indent=2, allow_nan=False),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Runtime",
            "",
            "```json",
            json.dumps(
                {
                    "environment": summary["environment"],
                    "measurements": summary["runtime"],
                    "reason": summary["runtime_reason"],
                },
                indent=2,
            ),
            "```",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def publish(
    summary: dict,
    output: Path,
    hashes: dict[str, str],
    issues: list[dict] | None = None,
    *,
    write_coordinate_metrics: bool = True,
) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    if summary["provenance"] == "synthetic":
        identifier = "synthetic-" + identifier
    destination = output / identifier
    # TemporaryDirectory owns only its fresh random directory, never older runs.
    with tempfile.TemporaryDirectory(prefix=".evaluation-", dir=output) as temporary:
        folder = Path(temporary)
        (folder / "evaluation_summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        (folder / "configuration.json").write_text(
            json.dumps(
                {
                    "metrics": summary["metric_configuration"],
                    "evaluator_source_sha256": summary["evaluator_source_sha256"],
                    "predictions": summary["prediction_provenance"],
                    "input_sha256": hashes,
                },
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (folder / "evaluation_report.md").write_text(
            markdown(summary), encoding="utf-8"
        )
        for family, filename in (
            ("detection", "detection_metrics.csv"),
            ("tracking", "tracking_metrics.csv"),
            ("teams", "team_classification_metrics.csv"),
        ):
            overall = summary["team_classification" if family == "teams" else family]
            rows = [
                {"clip_id": name, **item[family]}
                for name, item in summary["per_clip"].items()
            ]
            rows.append({"clip_id": "OVERALL", **overall})
            write_csv(folder / filename, rows, ["clip_id", "available", "reason"])
        positions = []
        for name, coordinates in [
            (key, value["coordinates"]) for key, value in summary["per_clip"].items()
        ] + [("OVERALL", summary["coordinates"])]:
            positions.extend(
                {"clip_id": name, "kind": family, **values}
                for family, values in coordinates.items()
            )
        if write_coordinate_metrics:
            write_csv(
                folder / "coordinate_metrics.csv",
                positions,
                ["clip_id", "kind", "available", "reason"],
            )
        write_csv(
            folder / "runtime_metrics.csv",
            summary["runtime"],
            [
                "clip_id",
                "stage",
                "available",
                "seconds",
                "frames",
                "frames_per_second",
                "reason",
            ],
        )
        confusion = []
        for name, metrics in [
            (key, value["teams"]) for key, value in summary["per_clip"].items()
        ] + [("OVERALL", summary["team_classification"])]:
            for truth, predictions in metrics.get("confusion_matrix", {}).items():
                confusion.extend(
                    {
                        "clip_id": name,
                        "ground_truth": truth,
                        "prediction": label,
                        "tracks": count,
                    }
                    for label, count in predictions.items()
                )
        write_csv(
            folder / "confusion_matrix.csv",
            confusion,
            ["clip_id", "ground_truth", "prediction", "tracks"],
        )
        write_csv(
            folder / "invalid_rows.csv",
            issues or [],
            ["kind", "file", "line", "reason"],
        )
        recheck(hashes)
        folder.rename(destination)
    return destination
