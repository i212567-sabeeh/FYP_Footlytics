"""SoccerNet-GSR 1.3 to the existing canonical evaluation observations.

Schema inspected on official SN-GSR-2025 valid/SNGS-021..023. The release uses
one-based JPEG filenames, opaque image IDs, pixel xywh boxes, clip-local IDs,
and left/right defending-goal team labels. Pitch positions are externally
calibrated bbox bottom-middle estimates, not independently surveyed positions.
See https://arxiv.org/html/2404.11335v1 sections 4.1 and 4.2.
"""

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.evaluation.schemas import Frame, InputError, Observation

VERSION = "soccernet-gsr-1.3-adapter-v1"
ROLES = {1: "player", 2: "goalkeeper", 3: "referee", 4: "ball", 7: "other"}
ROLE_POLICY = (
    "Score outfield players and goalkeepers; ignore referee/other person boxes; "
    "exclude ball, pitch and camera records. Apply identically to every clip."
)
COORDINATE_LIMITATION = (
    "The selected labels contain pitch-line polylines, but no explicit point-to-"
    "point calibration correspondences or camera parameter records. Four valid "
    "fit correspondences plus separate held-out landmarks have not been "
    "established. No homography is inferred from player GT positions; coordinate "
    "and held-out calibration accuracy are unavailable. Broadcast camera motion "
    "also prevents assuming a fixed calibration across the sequence."
)


def _real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise InputError(f"{name} must be finite")
    return result


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise InputError(f"{name} must be a positive integer")
    return value


def source_frame_number(filename: str) -> int:
    """Official 000001.jpg -> canonical zero-based frame 0; never use image_id."""
    if not isinstance(filename, str) or not re.fullmatch(r"[0-9]{6}\.jpg", filename):
        raise InputError("Expected a six-digit SoccerNet JPEG filename")
    source = int(filename[:6])
    if source < 1:
        raise InputError("SoccerNet JPEG frame numbering is one-based")
    return source - 1


def pixel_box(box: Mapping, width: int, height: int) -> tuple[float, ...]:
    """bbox_image x/y/w/h are original pixels; do not guess normalization."""
    if box.get("normalized", False):
        raise InputError("GSR 1.3 bbox_image must use pixel coordinates")
    try:
        x, y, w, h = (_real(box[key], key) for key in ("x", "y", "w", "h"))
    except KeyError as error:
        raise InputError("Missing bbox_image x/y/w/h") from error
    result = (x, y, x + w, y + h)
    if not (0 <= x < x + w <= width and 0 <= y < y + h <= height):
        raise InputError("Invalid or out-of-image SoccerNet bounding box")
    for key, expected in (("x_center", x + w / 2), ("y_center", y + h / 2)):
        if key in box and abs(_real(box[key], key) - expected) > 1e-6:
            raise InputError("Inconsistent bbox_image centre and xywh fields")
    return result


def convert_soccernet_pitch_to_footlytics(
    x: float,
    y: float,
    *,
    source_length_metres: float,
    source_width_metres: float,
    target_length_metres: float,
    target_width_metres: float,
) -> tuple[float, float]:
    """Centre origin -> far-left corner; X right along length, Y toward camera.

    GSR uses metres and a documented 105 x 68 model (not measured stadium
    dimensions). All dimensions are explicit here. No axis swap or sign flip is
    required for FOOTLYTICS' matching axis orientation. Rescaling, when requested,
    is explicit. Off-pitch coordinates are retained, never silently clipped.
    """
    values = [
        _real(value, name)
        for value, name in (
            (x, "x"),
            (y, "y"),
            (source_length_metres, "source length"),
            (source_width_metres, "source width"),
            (target_length_metres, "target length"),
            (target_width_metres, "target width"),
        )
    ]
    x, y, length, width, target_length, target_width = values
    if min(length, width, target_length, target_width) <= 0:
        raise InputError("Pitch dimensions must be positive metres")
    return (
        (x + length / 2) * target_length / length,
        (y + width / 2) * target_width / width,
    )


def team_mapping_from_reference_colors(
    references: Mapping[str, Sequence[float]],
) -> dict[str, str]:
    """Name GT teams by independent reference CIE Lab order, before inference.

    Phase 8 names its centroids by ascending (L,a,b), with no home/away meaning.
    References must come from human-labelled outfield jersey crops, never from
    predicted clusters, manual overrides, or a permutation chosen to raise scores.
    This function has no prediction/accuracy inputs and does not run clustering.
    """
    if set(references) != {"left", "right"}:
        raise InputError("Independent jersey references for both teams are required")
    colors = {}
    for label, values in references.items():
        if len(values) != 3:
            raise InputError("Jersey reference must be a CIE Lab triplet")
        color = tuple(_real(value, "Lab reference") for value in values)
        if not 0 <= color[0] <= 100 or any(abs(v) > 128 for v in color[1:]):
            raise InputError("Invalid CIE Lab reference")
        colors[label] = color
    if colors["left"] == colors["right"]:
        raise InputError("Equal jersey references cannot establish team ordering")
    return dict(
        zip(sorted(colors, key=colors.__getitem__), ("team_a", "team_b"), strict=True)
    )


@dataclass
class ConvertedClip:
    clip_id: str
    fps: float
    width: int
    height: int
    source_frame_count: int
    source_images: list[dict]
    frames: list[Frame]
    observations: list[Observation]
    diagnostics: dict


def _images(data: dict, count: int) -> tuple[dict, float, list[dict]]:
    info = data["info"]
    if str(info["version"]) != "1.3":
        raise InputError("Only the inspected GSR annotation version 1.3 is supported")
    if not re.fullmatch(r"SNGS-[0-9]{3}", info["name"]):
        raise InputError("Invalid SoccerNet clip name")
    fps = _real(info["frame_rate"], "frame rate")
    length = _positive_integer(info["seq_length"], "sequence length")
    if type(count) is not int or fps <= 0 or length > 10000 or not 1 <= count <= length:
        raise InputError("Invalid frame rate or bounded frame selection")
    images = sorted(
        data["images"], key=lambda image: source_frame_number(image["file_name"])
    )
    if len(images) != length or [
        source_frame_number(im["file_name"]) for im in images
    ] != list(range(length)):
        raise InputError("Missing or duplicate source frames")
    ids = [im["image_id"] for im in images]
    if (
        any(not isinstance(value, str) or not value for value in ids)
        or len(set(ids)) != length
    ):
        raise InputError("Invalid or duplicate image_id")
    dimensions = set()
    for im in images:
        dimensions.add(
            (
                _positive_integer(im["width"], "width"),
                _positive_integer(im["height"], "height"),
            )
        )
    if len(dimensions) != 1:
        raise InputError("Source image dimensions changed within the clip")
    for im in images[:count]:
        if im["is_labeled"] is not True or im["has_labeled_person"] is not True:
            raise InputError("Selected frames must have reviewed person annotations")
        if im["ignore_regions_x"] or im["ignore_regions_y"]:
            raise InputError("Polygon ignore regions need an explicit canonical policy")
    return info, fps, images


def convert_annotations(
    data: dict, *, frame_count: int, team_mapping: Mapping[str, str]
) -> ConvertedClip:
    """Convert the predetermined first N consecutive frames, rejecting bad GT."""
    if set(team_mapping) != {"left", "right"} or set(team_mapping.values()) != {
        "team_a",
        "team_b",
    }:
        raise InputError("Explicit left/right-to-canonical team mapping required")
    try:
        info, fps, images = _images(data, frame_count)
        selected = {
            im["image_id"]: number for number, im in enumerate(images[:frame_count])
        }
        all_ids = {im["image_id"] for im in images}
        width, height = images[0]["width"], images[0]["height"]
        observations = []
        seen, identities = set(), {}
        roles = Counter()
        for annotation in data["annotations"]:
            if annotation["image_id"] not in all_ids:
                raise InputError("Annotation references an unknown source image")
            if annotation["image_id"] not in selected:
                continue
            category = annotation["category_id"]
            if category in (5, 6):
                continue
            if category not in ROLES:
                raise InputError("Unknown SoccerNet object category")
            role = annotation["attributes"]["role"]
            if annotation["supercategory"] != "object" or role != ROLES[category]:
                raise InputError("Object category and role disagree")
            roles[role] += 1
            if role == "ball":
                continue
            frame = selected[annotation["image_id"]]
            identity = str(_positive_integer(annotation["track_id"], "track_id"))
            if (frame, identity) in seen:
                raise InputError("Duplicate GT Track ID in a frame")
            seen.add((frame, identity))
            ignored = role in {"referee", "other"}
            source_team = annotation["attributes"]["team"]
            if ignored:
                team = "official"
            elif source_team is None:
                team = "unknown"
            elif source_team in team_mapping:
                team = team_mapping[source_team]
            else:
                raise InputError("Unknown SoccerNet team label")
            signature = (role, source_team)
            if identity in identities and identities[identity] != signature:
                raise InputError("A GT identity changes role or team")
            identities[identity] = signature
            pitch = annotation["bbox_pitch"]
            if pitch is not None:
                pitch = convert_soccernet_pitch_to_footlytics(
                    pitch["x_bottom_middle"],
                    pitch["y_bottom_middle"],
                    source_length_metres=105,
                    source_width_metres=68,
                    target_length_metres=105,
                    target_width_metres=68,
                )
            observations.append(
                Observation(
                    frame,
                    frame / fps,
                    pixel_box(annotation["bbox_image"], width, height),
                    identity,
                    team,
                    ignored,
                    pitch=pitch,
                )
            )
        observations.sort(key=lambda row: (row.frame, int(row.track_id)))
        return ConvertedClip(
            info["name"],
            fps,
            width,
            height,
            len(images),
            images,
            [Frame(n, n / fps, True) for n in range(frame_count)],
            observations,
            {
                "source_annotation_version": info["version"],
                "roles": dict(roles),
                "selected_frames": frame_count,
                "source_frames": len(images),
                "gt_person_boxes": len(observations),
                "ignored_boxes": sum(r.ignored for r in observations),
                "gt_person_tracks": len(identities),
                "role_policy": ROLE_POLICY,
                "coordinate_accuracy_limitation": COORDINATE_LIMITATION,
            },
        )
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError(f"Malformed SoccerNet annotation: {error}") from error


def select_distinct_source_games(
    records: Sequence[Mapping], count: int = 3
) -> list[str]:
    """Metadata-only sorted selection; never accepts predictions or quality scores."""
    if type(count) is not int or not 1 <= count <= 5:
        raise InputError("Select between one and five distinct source games")
    clips = {}
    for record in records:
        clip_id = record.get("clip_id")
        game_id = record.get("game_id")
        if (
            not isinstance(clip_id, str)
            or not re.fullmatch(r"SNGS-[0-9]{3}", clip_id)
            or clip_id in clips
            or isinstance(game_id, bool)
            or not isinstance(game_id, (str, int))
            or not str(game_id).isdigit()
            or int(game_id) < 1
        ):
            raise InputError("Invalid or duplicate source-game selection metadata")
        clips[clip_id] = str(int(game_id))
    selected, games = [], set()
    for clip_id, game_id in sorted(clips.items()):
        if game_id in games:
            continue
        selected.append(clip_id)
        games.add(game_id)
        if len(selected) == count:
            return selected
    raise InputError("Fewer than the requested distinct source games are available")
