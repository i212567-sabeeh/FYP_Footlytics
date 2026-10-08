"""SoccerNet report orchestration; all scoring uses the existing Phase 15 code."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from app.evaluation.adapters.soccernet_gsr import COORDINATE_LIMITATION
from app.evaluation.inputs import load_dataset, sha256
from app.evaluation.reporting import evaluate, publish
from app.evaluation.runtime import environment
from app.evaluation.schemas import EvaluationConfig, InputError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Score only the first preselected clip with saved predictions",
    )
    args = parser.parse_args()
    config = EvaluationConfig()
    dataset, clips, predictions, hashes = load_dataset(
        args.dataset, args.predictions, config, allow_synthetic=False
    )
    provenance_path = args.dataset.parent / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    if predictions.pipeline_config != provenance["pipeline_config"]:
        raise InputError(
            "Prediction configuration does not match the pre-inference freeze"
        )
    if args.smoke:
        clips = clips[:1]
        dataset = dataset.model_copy(update={"clips": dataset.clips[:1]})
    if not clips or any(
        c.detections is None or c.tracks is None or c.automatic_teams is None
        for c in clips
    ):
        raise InputError(
            "Every selected clip requires validated real pipeline artifacts"
        )
    hashes[str(provenance_path.resolve())] = sha256(provenance_path)
    runtime_details = {}
    for clip in clips:
        cache = args.predictions.parent / clip.clip.clip_id / "prediction.json"
        details = json.loads(cache.read_text())
        hashes[str(cache.resolve())] = sha256(cache)
        runtime_details[clip.clip.clip_id] = {
            "model_load_seconds_this_process": details[
                "model_load_seconds_this_process"
            ],
            "diagnostics": details["diagnostics"],
        }
    start = perf_counter()
    summary = evaluate(
        dataset, clips, predictions, config, environment(probe_torch=True)
    )
    summary["scoring_seconds"] = perf_counter() - start
    summary["notice"] = (
        "Real FOOTLYTICS results on a small predetermined SoccerNet-GSR "
        "validation subset; not an official SoccerNet leaderboard "
        "submission"
    )
    games = sorted(
        {provenance["clips"][c.clip.clip_id]["source_info"]["game_id"] for c in clips}
    )
    summary["external_dataset"] = {
        "source_game_ids": games,
        "source_game_count": len(games),
        "dataset_name": "SoccerNet Game State Reconstruction",
        "dataset_version": "1.3",
        "release_repository": provenance["selection"]["repository"],
        "release_revision": provenance["selection"]["revision"],
        "official_source": "https://huggingface.co/datasets/SoccerNet/SN-GSR-2025",
        "split": "valid",
        "selected_clip_ids": [c.clip.clip_id for c in clips],
        "selection_method": provenance["selection"]["selection_method"],
        "frame_range": (
            "source JPEG 000001..000150; canonical 0..149 at 25 FPS, 6 seconds per clip"
        ),
        "sampling_policy": provenance["selection"]["sampling_policy"],
        "role_filtering": provenance["role_policy"],
        "team_label_mapping": {
            c.clip.clip_id: provenance["clips"][c.clip.clip_id]["team_mapping"]
            for c in clips
        },
        "coordinate_conversion": provenance["coordinate_system"],
        "pixel_verification": {
            c.clip.clip_id: provenance["clips"][c.clip.clip_id]["pixel_verification"]
            for c in clips
        },
        "frame_alignment": {
            c.clip.clip_id: provenance["clips"][c.clip.clip_id]["frame_alignment"]
            for c in clips
        },
        "initialization_and_runtime_diagnostics": runtime_details,
        "source_provenance": provenance,
    }
    for coordinates in [summary["coordinates"]] + [
        v["coordinates"] for v in summary["per_clip"].values()
    ]:
        for result in coordinates.values():
            if not result["available"]:
                result["reason"] = COORDINATE_LIMITATION
    summary["limitations"] += [
        (
            f"{len(clips)} deterministically selected clips from {len(games)} source "
            f"games; {sum(c.clip.frame_count for c in clips)} frames represent "
            f"only {sum(c.clip.duration_seconds for c in clips):g} seconds. "
            "This small subset does not establish broad football-domain accuracy."
        ),
        (
            "Moving broadcast footage, zoom, compression, player scale and "
            "stadium lighting differ from user-recorded 11v11/5v5 footage."
        ),
        (
            "Team A/B are colour-ordered cluster names, not home/away "
            "identities. Mapping uses jersey-color references extracted from "
            "human-labelled SoccerNet team annotations before inference; "
            "no accuracy-maximizing "
            "permutation or manual override is used."
        ),
        (
            "SoccerNet pitch positions are externally calibrated and "
            "temporally smoothed estimates, not independently surveyed "
            "athlete locations. No coordinate accuracy is published in this "
            "run."
        ),
        (
            "Official source JPEGs are packed into PNG-in-MOV with all "
            "decoded pixels verified identical; storage/decode overhead "
            "differs from compressed match uploads."
        ),
        (
            "Pitch ROI is unavailable without verified corner "
            "correspondences; unlabelled spectators or sidelines may "
            "contribute false positives."
        ),
        (
            "No production CV implementation or threshold was changed. Local "
            "user-footage annotation could complement this external "
            "evaluation."
        ),
    ]
    available = any(item["available"] for item in summary["coordinates"].values())
    output = publish(summary, args.output, hashes, write_coordinate_metrics=available)
    print(f"SoccerNet evaluation published: {output}", flush=True)


if __name__ == "__main__":
    main()
