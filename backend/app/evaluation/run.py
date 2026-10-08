"""Explicit, offline CLI: never scans or processes production Match storage."""

import argparse
import csv
import json
import sys
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.evaluation.configuration import pipeline_snapshot
from app.evaluation.inputs import load_dataset
from app.evaluation.reporting import evaluate, publish
from app.evaluation.runtime import environment
from app.evaluation.schemas import Dataset, EvaluationConfig, InputError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Evaluate explicitly declared FOOTLYTICS validation data; "
            "no training or automatic video processing"
        )
    )
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dataset", type=Path, help="Canonical dataset JSON manifest")
    mode.add_argument(
        "--inventory",
        action="store_true",
        help="Report missing validation data without claiming accuracy",
    )
    mode.add_argument(
        "--write-config",
        type=Path,
        help="Write a CV-only settings snapshot; capture at prediction generation time",
    )
    result.add_argument(
        "--predictions", type=Path, help="Verified saved prediction manifest"
    )
    result.add_argument(
        "--clips", type=Path, default=PROJECT_ROOT / "data/validation_clips"
    )
    result.add_argument(
        "--annotations", type=Path, default=PROJECT_ROOT / "data/annotations"
    )
    result.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "storage/evaluation"
    )
    result.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Label all output SYNTHETIC TEST, never empirical accuracy",
    )
    result.add_argument(
        "--iou",
        type=float,
        default=0.5,
        help="Count/tracking/association IoU; AP50 always uses 0.50",
    )
    result.add_argument(
        "--probe-torch",
        action="store_true",
        help="Import torch to record real CUDA availability; does not run inference",
    )
    return result


def empty_dataset(description: str) -> Dataset:
    return Dataset(
        description=description,
        provenance="human",
        annotation_author="unavailable",
        annotation_notes="No validated human annotations have been evaluated",
        independent_ground_truth=False,
        clips=[],
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.write_config:
        with args.write_config.open("x", encoding="utf-8") as stream:
            json.dump(pipeline_snapshot(Settings()), stream, indent=2, allow_nan=False)
        print(f"CV configuration written: {args.write_config}")
        return 0
    if args.predictions and not args.dataset:
        parser().error("--predictions requires --dataset")
    try:
        config = EvaluationConfig(
            detection_iou=args.iou, tracking_iou=args.iou, association_iou=args.iou
        )
    except ValidationError as error:
        parser().error(str(error))
    machine = environment(probe_torch=args.probe_torch)
    start = perf_counter()
    try:
        if args.inventory:
            dataset = empty_dataset(
                "Validation input inventory only; no empirical accuracy measured"
            )
            summary = evaluate(dataset, [], None, config, machine)
            video_files = sorted(
                str(p.relative_to(args.clips))
                for p in args.clips.rglob("*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"}
            )
            annotation_files = sorted(
                str(p.relative_to(args.annotations))
                for p in args.annotations.rglob("*")
                if p.is_file()
                and p.suffix in {".csv", ".json"}
                and ".template." not in p.name
            )
            summary["inventory"] = {
                "video_files": video_files,
                "annotation_files": annotation_files,
                "note": "Listed files are not automatically validated "
                "or counted as annotations",
            }
            hashes = {}
        else:
            dataset, clips, predictions, hashes = load_dataset(
                args.dataset,
                args.predictions,
                config,
                allow_synthetic=args.allow_synthetic,
            )
            summary = evaluate(dataset, clips, predictions, config, machine)
        summary["scoring_seconds"] = perf_counter() - start
        path = publish(summary, args.output, hashes)
    except (InputError, ValidationError, ValueError, OSError, csv.Error) as error:
        summary = evaluate(
            empty_dataset("Input validation failed; no accuracy metrics produced"),
            [],
            None,
            config,
            machine,
        )
        summary.update(
            status="invalid_inputs",
            error=str(error),
            scoring_seconds=perf_counter() - start,
        )
        if args.allow_synthetic:
            summary.update(
                provenance="synthetic",
                notice="SYNTHETIC TEST — NOT REAL MODEL ACCURACY",
            )
        path = publish(summary, args.output, {}, getattr(error, "issues", []))
        print(
            f"Evaluation rejected: {error}\nDiagnostic output: {path}", file=sys.stderr
        )
        return 2
    print(
        f"{summary['notice']}\nStatus: {summary['status']}; "
        f"clips: {summary['clip_count']}; "
        f"annotated frames: {summary['annotated_frames']}\nOutput: {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
