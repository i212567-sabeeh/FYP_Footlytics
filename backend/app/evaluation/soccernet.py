"""Prepare a bounded SoccerNet subset for the existing offline evaluator.

Run only on the independently selected, checksum-verified official source files.
This command never runs a model, changes thresholds, or creates GT from predictions.
"""

import argparse
import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from app.core.config import Settings
from app.cv.team_classifier import jersey_crop, jersey_feature
from app.evaluation.adapters.soccernet_gsr import (
    COORDINATE_LIMITATION,
    ROLE_POLICY,
    VERSION,
    convert_annotations,
    pixel_box,
    select_distinct_source_games,
    source_frame_number,
    team_mapping_from_reference_colors,
)
from app.evaluation.configuration import (
    digest_json,
    evaluator_digest,
    pipeline_snapshot,
)
from app.evaluation.inputs import checked_file, load_dataset, sha256
from app.evaluation.schemas import Clip, Dataset, EvaluationConfig, FileRef, InputError


def reference(path: Path, base: Path) -> FileRef:
    return FileRef(
        path=Path(os.path.relpath(path, base)).as_posix(), sha256=sha256(path)
    )


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def jersey_references(data: dict, raw: Path, settings: Settings) -> dict:
    """Independent naming evidence: GT outfield crops at frames 0,15,30.

    Only colour extraction is reused. No classifier, clustering, predictions,
    inferred identity, or automatic/manual team output is consulted.
    """
    colors = {"left": [], "right": []}
    records = []
    by_id = {im["image_id"]: im for im in data["images"]}
    for im in data["images"]:
        frame = source_frame_number(im["file_name"])
        if frame not in {0, 15, 30}:
            continue
        image = cv2.imread(str(raw / "img1" / im["file_name"]))
        if image is None or image.shape[:2] != (im["height"], im["width"]):
            raise InputError("Missing or wrong-sized jersey reference image")
        for annotation in data["annotations"]:
            if (
                annotation["image_id"] != im["image_id"]
                or annotation["category_id"] != 1
            ):
                continue
            team = annotation["attributes"]["team"]
            if team not in colors:
                continue
            box = pixel_box(annotation["bbox_image"], im["width"], im["height"])
            crop = jersey_crop(image, box, settings)
            appearance = jersey_feature(crop) if crop is not None else None
            if appearance is not None:
                colors[team].append(appearance.color)
                records.append(
                    {
                        "source_image": by_id[annotation["image_id"]]["file_name"],
                        "gt_track_id": annotation["track_id"],
                        "team": team,
                        "lab": appearance.color,
                    }
                )
    if any(len(values) < 3 for values in colors.values()):
        raise InputError("Insufficient independent jersey reference crops")
    median = {
        team: np.median(values, axis=0).tolist() for team, values in colors.items()
    }
    return {
        "method": (
            "Jersey-color references extracted from human-labelled SoccerNet "
            "team annotations: median CIE Lab of outfield torso crops on fixed "
            "frames 0,15,30; ascending (L,a,b); frozen before predictions"
        ),
        "soccernet_to_footlytics": team_mapping_from_reference_colors(median),
        "reference_median_lab": median,
        "reference_samples": records,
        "manual_overrides_used": False,
        "posthoc_permutation_alignment": False,
    }


def lossless_video(raw: Path, converted, target: Path) -> list[dict]:
    """PNG MOV packs decoded official JPEGs without resizing or added pixel loss."""
    if target.exists():
        raise InputError("Refusing to overwrite a prepared video")
    writer = cv2.VideoWriter(
        str(target),
        cv2.VideoWriter_fourcc(*"png "),
        converted.fps,
        (converted.width, converted.height),
    )
    if not writer.isOpened():
        raise InputError("PNG MOV video encoding is unavailable")
    try:
        for frame in converted.frames:
            im = cv2.imread(
                str(raw / "img1" / converted.source_images[frame.number]["file_name"])
            )
            if im is None or im.shape != (converted.height, converted.width, 3):
                raise InputError("Source JPEG is missing or has unexpected dimensions")
            writer.write(im)
    finally:
        writer.release()
    return verify_production_pixels(raw, converted, target)


def verify_production_pixels(raw: Path, converted, target: Path) -> list[dict]:
    """Verify every frame through the actual production decoder, not a surrogate."""
    from app.cv.video import VideoFrames

    alignment = []
    checkpoints = {0, len(converted.frames) // 2, len(converted.frames) - 1}
    checked = 0
    with VideoFrames(target) as source:
        if (
            source.total_frames != len(converted.frames)
            or abs(source.fps - converted.fps) > 1e-6
        ):
            raise InputError("Production video FPS/frame count differs from source")
        for decoded, expected in zip(source, converted.frames, strict=True):
            original = cv2.imread(
                str(
                    raw / "img1" / converted.source_images[expected.number]["file_name"]
                )
            )
            if decoded.number != expected.number or not np.array_equal(
                decoded.image, original
            ):
                raise InputError(
                    "Production-decoded pixels/order differ from the official JPEG"
                )
            if abs(decoded.timestamp_seconds - expected.timestamp) > 0.001:
                raise InputError(
                    "Production timestamp does not match source frame schedule"
                )
            checked += 1
            if expected.number in checkpoints:
                alignment.append(
                    {
                        "source_filename": converted.source_images[expected.number][
                            "file_name"
                        ],
                        "source_image_id": converted.source_images[expected.number][
                            "image_id"
                        ],
                        "video_frame": decoded.number,
                        "timestamp_seconds": decoded.timestamp_seconds,
                        "pixels_identical": True,
                    }
                )
    if checked != len(converted.frames):
        raise InputError("Production decoding did not cover the full selected interval")
    return alignment


def prepare(root: Path, *, output: Path | None = None) -> Path:
    selection_path = root / "manifests/selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selected = selection["selected_clip_ids"]
    audit = selection["selection_audit"]
    if [record["clip_id"] for record in audit] != sorted(
        selection["validation_clip_ids"]
    )[: len(audit)]:
        raise InputError(
            "Selection audit must cover consecutive sorted validation metadata"
        )
    if selected != select_distinct_source_games(audit):
        raise InputError(
            "Selection differs from the frozen distinct-source-game policy"
        )
    # Verify all downloaded bytes against the persisted download hashes before use.
    for family in ("annotations", "images"):
        download = json.loads((root / f"manifests/download_{family}.json").read_text())
        for member in download["members"]:
            path = root / "raw" / member["name"]
            if (
                not path.resolve().is_relative_to((root / "raw").resolve())
                or sha256(path) != member["sha256"]
            ):
                raise InputError("Downloaded source hash mismatch")
    settings = Settings()
    snapshot = pipeline_snapshot(settings)
    if settings.detection_frame_stride != 1:
        raise InputError("Consecutive tracking evaluation requires existing stride=1")
    out = output or root / "converted" / "distinct-games-v1"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "dataset.json").exists():
        raise InputError("Prepared dataset already exists; validate/reuse it instead")
    provenance = {
        "selection": selection,
        "selection_sha256": sha256(selection_path),
        "source_manifest_sha256": {
            name: sha256(root / "manifests" / name)
            for name in (
                "download_annotations.json",
                "download_images.json",
                "final_visual_alignment_review.json",
            )
        },
        "visual_alignment_review": json.loads(
            (root / "manifests/final_visual_alignment_review.json").read_text(
                encoding="utf-8"
            )
        ),
        "prepared_at": datetime.now(UTC).isoformat(),
        "adapter_version": VERSION,
        "adapter_sha256": sha256(Path(__file__).parent / "adapters/soccernet_gsr.py"),
        "evaluator_sha256": evaluator_digest(),
        "pipeline_config": snapshot,
        "pipeline_config_sha256": digest_json(snapshot),
        "metric_config": EvaluationConfig().model_dump(),
        "role_policy": ROLE_POLICY,
        "coordinate_system": {
            "source_origin": "pitch centre",
            "source_x": "towards right goal",
            "source_y": "towards camera",
            "units": "metres",
            "source_model_length": 105,
            "source_model_width": 68,
            "conversion": "X=x+52.5; Y=y+34; no scaling for this model",
            "ground_point": "bbox bottom-middle",
            "reference_method": (
                "External camera calibration derived from human pitch lines; not "
                "surveyed athlete positions"
            ),
            "accuracy_limitation": COORDINATE_LIMITATION,
        },
        "clips": {},
    }
    clips = []
    for clip_id in selected:
        raw = root / "raw" / clip_id
        source = raw / "Labels-GameState.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        selected_info = next(record for record in audit if record["clip_id"] == clip_id)
        if str(data["info"]["game_id"]) != selected_info["game_id"]:
            raise InputError("Full annotation disagrees with frozen game metadata")
        mapping = jersey_references(data, raw, settings)
        converted = convert_annotations(
            data, frame_count=150, team_mapping=mapping["soccernet_to_footlytics"]
        )
        if converted.clip_id != clip_id:
            raise InputError("Annotation clip name disagrees with selected source")
        destination = out / clip_id
        destination.mkdir(exist_ok=True)
        write_json(destination / "team_mapping.json", mapping)
        video = destination / "frames-000001-000150.mov"
        previous_path = root / "converted" / "dataset.json"
        previous = (
            Dataset.model_validate_json(previous_path.read_text(encoding="utf-8"))
            if previous_path.exists()
            else None
        )
        previous_clip = (
            next((item for item in previous.clips if item.clip_id == clip_id), None)
            if previous
            else None
        )
        if previous_clip is not None:
            video = checked_file(previous_path.parent, previous_clip.video)
            alignment = verify_production_pixels(raw, converted, video)
        else:
            alignment = lossless_video(raw, converted, video)
        frame_csv, boxes_csv = destination / "frames.csv", destination / "boxes.csv"
        with frame_csv.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ("clip_id", "frame_number", "timestamp_seconds", "tracking_evaluable")
            )
            writer.writerows(
                (clip_id, f.number, f.timestamp, "true") for f in converted.frames
            )
        with boxes_csv.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "clip_id",
                    "frame_number",
                    "timestamp_seconds",
                    "ground_truth_track_id",
                    "team_label",
                    "ignored",
                    "x1",
                    "y1",
                    "x2",
                    "y2",
                    "pitch_x",
                    "pitch_y",
                )
            )
            writer.writerows(
                (
                    clip_id,
                    r.frame,
                    r.timestamp,
                    r.track_id,
                    r.team,
                    str(r.ignored).lower(),
                    *r.box,
                    *(r.pitch or ("", "")),
                )
                for r in converted.observations
            )
        clips.append(
            Clip(
                clip_id=clip_id,
                video=reference(video, out),
                frames=reference(frame_csv, out),
                annotations=reference(boxes_csv, out),
                fps=converted.fps,
                frame_count=150,
                width=converted.width,
                height=converted.height,
                duration_seconds=150 / converted.fps,
                football_format="11v11",
                conditions=(
                    "SoccerNet broadcast moving-camera footage; first 150 consecutive "
                    "source frames; "
                    f"source game_id={data['info']['game_id']}"
                ),
                pitch_length_metres=105,
                pitch_width_metres=68,
                independent_pitch_ground_truth=True,
                pitch_ground_truth_method=(
                    "SoccerNet v1.3 externally calibrated/smoothed bbox bottom-middle "
                    "positions; independent of FOOTLYTICS but not surveyed athlete "
                    "measurements"
                ),
                team_mapping={"team_a": "team_a", "team_b": "team_b"},
                team_mapping_basis=mapping["method"],
            )
        )
        provenance["clips"][clip_id] = {
            "source_annotation_sha256": sha256(source),
            "source_info": data["info"],
            "diagnostics": converted.diagnostics,
            "team_mapping": mapping,
            "frame_alignment": alignment,
            "all_150_decoded_frames_pixel_identical": True,
            "pixel_verification": {
                "checked_frames": 150,
                "mismatched_frames": 0,
                "frame_count": 150,
                "width": converted.width,
                "height": converted.height,
                "fps": converted.fps,
                "decoder": "app.cv.video.VideoFrames",
            },
            "prepared_video_bytes": video.stat().st_size,
            "video_sha256": sha256(video),
            "gt_annotation_objects_in_full_clip": len(data["annotations"]),
        }
        print(
            f"Prepared and pixel-verified {clip_id}: 150 frames, "
            f"{len(converted.observations)} person GT rows",
            flush=True,
        )
    dataset = Dataset(
        description=(
            "SoccerNet-GSR 1.3 / SN-GSR-2025 valid: first clip from each of "
            "three distinct source games, "
            "first 150 consecutive frames each"
        ),
        provenance="human",
        annotation_author="SoccerNet authors and human annotators",
        annotation_notes=(
            "Human keyframe annotations with dataset interpolation; "
            "independent of FOOTLYTICS. Explicit referee ignores. Bbox-pitch "
            "values derive from external calibration; no metre-based accuracy "
            "claimed without valid independent calibration inputs."
        ),
        independent_ground_truth=True,
        clips=clips,
    )
    dataset_path = out / "dataset.json"
    write_json(dataset_path, dataset.model_dump(mode="json"))
    write_json(out / "provenance.json", provenance)
    load_dataset(dataset_path, None, EvaluationConfig(), allow_synthetic=False)
    print(f"Canonical annotation validation passed: {dataset_path}", flush=True)
    return dataset_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    prepare(args.root.resolve(), output=args.output.resolve() if args.output else None)


if __name__ == "__main__":
    main()
