# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Score automatic team classification on SoccerNet-GSR from cached tracks; no YOLO.

Replays the production classify_tracking over saved ByteTrack output, decoding
frames from the dataset JPEGs (verified pixel-identical to the frozen MOV
decode), and scores each ground-truth identity with the unchanged evaluator.
Variants change only declared settings (--set NAME=VALUE). Run from the
repository root; the output directory must be new.
"""

import argparse
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.cv.team_classifier import jersey_crop, jersey_feature
from app.cv.team_colors import fit_prototype, validate_prototypes
from app.cv.team_pipeline import classify_tracking
from app.evaluation.inputs import load_dataset
from app.evaluation.metrics import assign, grouped, iou_matrix
from app.evaluation.schemas import EvaluationConfig
from app.evaluation.teams import evaluate_teams
from app.schemas.detection import DetectionSummary
from app.schemas.tracking import TrackingSummary


def parse_override(text: str) -> tuple[str, object]:
    name, _, value = text.partition("=")
    if name not in Settings.model_fields or not name.startswith("team_"):
        raise SystemExit(f"Only team_* settings can be overridden, not {name!r}")
    return name, json.loads(value)


def summaries(clip, tracks_path: Path, settings: Settings):
    with tracks_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    frames = clip.frame_count
    detection = DetectionSummary(
        processed_frames=frames,
        decoded_frames=frames,
        total_detections=len(rows),
        average_detections_per_processed_frame=len(rows) / frames,
        frame_stride=1,
        frame_width=clip.width,
        frame_height=clip.height,
        timestamp_fallback_frames=0,
        model="cached",
        device="cpu",
        confidence_threshold=settings.yolo_confidence,
        inference_image_size=settings.yolo_image_size,
        roi_filter_applied=False,
        roi_skip_reason="Offline replay of cached tracks",
        calibration_id=0,
        calibration_updated_at=datetime.now(UTC),
    )
    tracking = TrackingSummary(
        processed_frames=frames,
        total_detections=len(rows),
        total_track_rows=len(rows),
        unique_tracks=len({row["track_id"] for row in rows}),
        frame_stride=1,
        frame_width=clip.width,
        frame_height=clip.height,
        detection_job_id=0,
        detection_attempt=0,
        track_high_thresh=settings.track_high_thresh,
        track_low_thresh=settings.track_low_thresh,
        track_match_thresh=settings.track_match_thresh,
        track_buffer=settings.track_buffer,
    )
    return detection, tracking


def officials_with_team(clip, labels: dict[str, str], threshold: float = 0.5):
    """Referees/officials (ignored by team scoring) whose best-overlapping track
    received Team A/B: a safety check, since officials must stay Unknown."""
    counts: dict[tuple[str, str], int] = {}
    gt_frames, pred_frames = grouped(clip.annotations), grouped(clip.tracks or [])
    for frame in clip.frames:
        gt = [r for r in gt_frames[frame.number] if r.track_id and r.team == "official"]
        pred = pred_frames[frame.number]
        for a, b, _ in assign(
            iou_matrix([r.box for r in gt], [r.box for r in pred]), threshold
        ):
            key = (gt[a].track_id, pred[b].track_id)
            counts[key] = counts.get(key, 0) + 1
    best: dict[str, tuple[str, int]] = {}
    for (official, track), count in counts.items():
        if count > best.get(official, ("", 0))[1]:
            best[official] = (track, count)
    labelled = sum(
        labels.get(track, "unknown") != "unknown" for track, _ in best.values()
    )
    return {"officials": len(best), "officials_with_team_label": labelled}


def seeded_prototypes(clip, mapping_path: Path, frame, settings, count: int):
    """User-seeded mode from human-labelled frame-0 outfield crops.

    Mirrors Set Team Colors: the backend measures each selected crop itself and
    fits a prototype with the unchanged validation rules. Like a user who is told
    a crop is too weak, take the first crops (reference order) that pass the
    per-crop quality check; if examples still disagree, retry with fewer.
    """
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    names = {
        key: TrackTeam(value)
        for key, value in mapping["soccernet_to_footlytics"].items()
    }
    boxes = {r.track_id: r.box for r in clip.annotations if r.frame == 0 and r.track_id}
    chosen = {team: [] for team in names.values()}
    for sample in mapping["reference_samples"]:
        team = names[sample["team"]]
        if sample["source_image"] == "000001.jpg" and len(chosen[team]) < count:
            crop = jersey_crop(frame, boxes[str(sample["gt_track_id"])], settings)
            feature = jersey_feature(crop) if crop is not None else None
            if (
                feature is not None
                and feature.quality >= settings.team_unknown_threshold
            ):
                chosen[team].append(feature)
    prototypes = {}
    for team, samples in chosen.items():
        for size in range(len(samples), 0, -1):
            try:
                prototypes[team] = fit_prototype(samples[:size], settings)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"No valid seed examples for {team.value}")
    validate_prototypes(prototypes)
    return prototypes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--frames-root", type=Path, required=True)
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument(
        "--seed-examples",
        type=int,
        default=0,
        help="Seeded mode: frame-0 labelled crops per team (0 = automatic mode)",
    )
    parser.add_argument(
        "--mapping-root",
        type=Path,
        help="Folder with <clip>/team_mapping.json reference samples (seeded mode)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    overrides = dict(parse_override(item) for item in args.overrides)
    settings = Settings(_env_file=None).model_copy(update=overrides)
    Settings(_env_file=None, **overrides)  # Validate the declared values.
    _, clips, predictions, _ = load_dataset(
        args.dataset, args.predictions, EvaluationConfig()
    )
    result = {
        "overrides": overrides,
        "mode": "user_seeded" if args.seed_examples else "automatic",
        "seed_examples_per_team": args.seed_examples,
        "clips": {},
    }
    for clip in clips:
        clip_id = clip.clip.clip_id
        tracks_path = args.predictions.parent / clip_id / "tracks.csv"
        detection, tracking = summaries(clip.clip, tracks_path, settings)
        folder = args.frames_root / clip_id / "img1"

        def load_frame(number, folder=folder):
            return cv2.imread(str(folder / f"{number + 1:06d}.jpg"), cv2.IMREAD_COLOR)

        prototypes = None
        if args.seed_examples:
            prototypes = seeded_prototypes(
                clip,
                args.mapping_root / clip_id / "team_mapping.json",
                load_frame(0),
                settings,
                args.seed_examples,
            )
        start = time.perf_counter()
        run = classify_tracking(
            tracks_path,
            detection,
            tracking,
            clip.clip.duration_seconds,
            settings,
            load_frame=load_frame,
            progress=lambda *_: None,
            prototypes=prototypes,
        )
        clip.automatic_teams = {str(p.track_id): p.team.value for p in run.predictions}
        result["clips"][clip_id] = {
            "seconds": time.perf_counter() - start,
            "sampled_frames": run.sampled_frames,
            "valid_samples": run.valid_samples,
            "tracks": len(run.predictions),
            "predicted": {
                team: sum(p.team.value == team for p in run.predictions)
                for team in ("team_a", "team_b", "unknown")
            },
            "diagnostics": run.diagnostics,
            "metrics": evaluate_teams([clip]),
            "safety": officials_with_team(clip, clip.automatic_teams),
        }
    result["overall"] = evaluate_teams(clips)
    result["overall"]["officials_with_team_label"] = sum(
        item["safety"]["officials_with_team_label"] for item in result["clips"].values()
    )
    result["overall"]["officials"] = sum(
        item["safety"]["officials"] for item in result["clips"].values()
    )
    (args.output / "results.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    overall = result["overall"]
    print(
        f"overrides={overrides} coverage={overall['coverage']:.4f} "
        f"classified={overall['classified_tracks']}/{overall['eligible_tracks']} "
        f"accuracy={overall['accuracy']:.4f} "
        f"accuracy_among_classified={overall['accuracy_among_classified']} "
        f"officials_labelled={overall['officials_with_team_label']}/"
        f"{overall['officials']} mode={result['mode']}"
    )
    for clip_id, item in result["clips"].items():
        print(
            f"  {clip_id}: {item['predicted']} unknown_reasons="
            f"{item['diagnostics'].get('unknown_reasons')} "
            f"samples={item['valid_samples']} t={item['seconds']:.1f}s"
        )


if __name__ == "__main__":
    main()
