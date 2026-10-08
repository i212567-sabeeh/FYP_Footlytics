"""Strict bounded CSV loading and content-based provenance checks."""

import csv
import hashlib
import math
from collections.abc import Callable
from pathlib import Path

import cv2

from app.evaluation.configuration import digest_json, validate_pipeline_snapshot
from app.evaluation.schemas import (
    CalibrationSnapshot,
    Clip,
    ClipData,
    Dataset,
    EvaluationConfig,
    FileRef,
    Frame,
    InputError,
    Landmark,
    Observation,
    Predictions,
)

BOX_COLUMNS = {"frame_number", "timestamp_seconds", "x1", "y1", "x2", "y2"}
GT_COLUMNS = BOX_COLUMNS | {"clip_id", "ground_truth_track_id", "team_label", "ignored"}
FRAME_COLUMNS = {"clip_id", "frame_number", "timestamp_seconds", "tracking_evaluable"}
LANDMARK_COLUMNS = {
    "clip_id",
    "landmark_id",
    "frame_number",
    "image_x",
    "image_y",
    "pitch_x",
    "pitch_y",
    "role",
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_file(base: Path, reference: FileRef) -> Path:
    path = (base / reference.path).resolve()
    if not path.is_file() or sha256(path) != reference.sha256:
        raise InputError(
            f"Missing or changed input: {reference.path}; refresh provenance"
        )
    return path


def number(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Numeric values must be finite")
    return result


def integer(value: str) -> int:
    result = int(value)
    if result < 0 or str(result) != value:
        raise ValueError("Frame identifiers must be non-negative canonical integers")
    return result


def boolean(value: str) -> bool:
    if value not in {"true", "false", "1", "0"}:
        raise ValueError("Boolean values must be true/false or 1/0")
    return value in {"true", "1"}


def read_rows(
    path: Path, columns: set[str], parse: Callable, limit: int, kind: str
) -> list:
    rows, issues = [], []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, strict=True)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not columns.issubset(header):
            raise InputError(
                f"{path.name}: missing or duplicate required columns ({kind})"
            )
        for line, row in enumerate(reader, 2):
            if line - 1 > limit:
                raise InputError(
                    f"{path.name}: exceeds the declared evaluation row limit"
                )
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Malformed CSV row")
                rows.append(parse(row))
            except (ValueError, KeyError, TypeError, OverflowError) as error:
                issues.append(
                    {
                        "kind": kind,
                        "file": path.name,
                        "line": line,
                        "reason": str(error),
                    }
                )
    if issues:
        raise InputError(
            f"{path.name}: {len(issues)} invalid {kind} rows; no metrics calculated",
            issues=issues,
        )
    return rows


def frame_values(row: dict, clip: Clip) -> tuple[int, float]:
    if "clip_id" in row and row["clip_id"] != clip.clip_id:
        raise ValueError("Unknown or incorrect clip_id")
    frame, timestamp = integer(row["frame_number"]), number(row["timestamp_seconds"])
    if not 0 <= frame < clip.frame_count or not 0 <= timestamp < clip.duration_seconds:
        raise ValueError("Frame or timestamp is outside this clip")
    return frame, timestamp


def box_values(row: dict, clip: Clip) -> tuple[float, float, float, float]:
    box = tuple(number(row[key]) for key in ("x1", "y1", "x2", "y2"))
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= clip.width and 0 <= y1 < y2 <= clip.height):
        raise ValueError("Bounding box must be ordered and inside the original image")
    return box


def optional_pitch(row: dict) -> tuple[float, float] | None:
    x, y = row.get("pitch_x", ""), row.get("pitch_y", "")
    if bool(x) != bool(y):
        raise ValueError("Pitch coordinates must contain both X and Y")
    return (number(x), number(y)) if x else None


def load_annotations(base: Path, clip: Clip, config: EvaluationConfig) -> ClipData:
    def parse_frame(row):
        frame, timestamp = frame_values(row, clip)
        return Frame(frame, timestamp, boolean(row["tracking_evaluable"]))

    frames = read_rows(
        checked_file(base, clip.frames), FRAME_COLUMNS, parse_frame, 10000, "annotation"
    )
    if not frames or [f.number for f in frames] != sorted({f.number for f in frames}):
        raise InputError("Reviewed frames must be nonempty, unique and sorted")
    if any(
        a.timestamp >= b.timestamp for a, b in zip(frames, frames[1:], strict=False)
    ):
        raise InputError("Reviewed timestamps must increase with frame number")
    by_frame = {f.number: f for f in frames}
    seen: set[tuple[int, str]] = set()
    teams: dict[str, str] = {}

    def parse(row):
        frame, timestamp = frame_values(row, clip)
        if frame not in by_frame or abs(by_frame[frame].timestamp - timestamp) > 0.001:
            raise ValueError("Annotation does not match a reviewed frame/timestamp")
        identity = row["ground_truth_track_id"] or None
        team = row["team_label"] or None
        if team not in {None, "team_a", "team_b", "unknown", "official"}:
            raise ValueError("Invalid team label")
        ignored = boolean(row["ignored"]) or team == "official"
        if by_frame[frame].tracking_evaluable and not ignored and not identity:
            raise ValueError("Tracking-evaluable players require a GT track ID")
        if identity:
            if (frame, identity) in seen:
                raise ValueError("Duplicate GT Track ID in the same frame")
            seen.add((frame, identity))
            if team in {"team_a", "team_b", "official"}:
                if identity in teams and teams[identity] != team:
                    raise ValueError("Conflicting team labels for one GT track")
                teams[identity] = team
        pitch = optional_pitch(row)
        if pitch is not None and (
            not clip.independent_pitch_ground_truth or clip.pitch_length_metres is None
        ):
            raise ValueError(
                "Player pitch GT requires independent evidence and Match dimensions"
            )
        return Observation(
            frame,
            timestamp,
            box_values(row, clip),
            identity,
            team,
            ignored,
            pitch=pitch,
        )

    annotations = read_rows(
        checked_file(base, clip.annotations),
        GT_COLUMNS,
        parse,
        config.max_rows_per_file,
        "annotation",
    )
    data = ClipData(clip, frames, annotations)
    if clip.landmarks:
        data.landmarks = load_landmarks(base, clip, config)
    return data


def load_landmarks(base: Path, clip: Clip, config: EvaluationConfig) -> list[Landmark]:
    seen_ids, seen_image, seen_pitch = set(), set(), set()

    def parse(row):
        if (
            row["clip_id"] != clip.clip_id
            or integer(row["frame_number"]) != clip.calibration_frame_number
        ):
            raise ValueError(
                "Landmarks must refer to the specified clip/calibration frame"
            )
        identifier, role = row["landmark_id"], row["role"]
        image = (number(row["image_x"]), number(row["image_y"]))
        pitch = (number(row["pitch_x"]), number(row["pitch_y"]))
        if not identifier or role not in {"fit", "validation"}:
            raise ValueError("Landmarks require an ID and fit/validation role")
        if not (0 <= image[0] <= clip.width and 0 <= image[1] <= clip.height):
            raise ValueError("Landmark image point outside the frame")
        if not (
            0 <= pitch[0] <= clip.pitch_length_metres
            and 0 <= pitch[1] <= clip.pitch_width_metres
        ):
            raise ValueError("Landmark pitch point outside the Match pitch")
        if identifier in seen_ids or image in seen_image or pitch in seen_pitch:
            raise ValueError("Duplicate landmark or reused fitting/validation point")
        seen_ids.add(identifier)
        seen_image.add(image)
        seen_pitch.add(pitch)
        return Landmark(identifier, image, pitch, role)

    return read_rows(
        checked_file(base, clip.landmarks),
        LANDMARK_COLUMNS,
        parse,
        config.max_rows_per_file,
        "annotation",
    )


def load_boxes(
    path: Path, data: ClipData, frames: set[int], family: str, config: EvaluationConfig
) -> list[Observation]:
    columns = BOX_COLUMNS | {"confidence"}
    if family != "detections":
        columns |= {"track_id"}
    if family == "coordinates":
        columns |= {"pitch_x", "pitch_y"}
    seen, timestamps = set(), {}
    reviewed = {f.number: f.timestamp for f in data.frames}

    def parse(row):
        frame, timestamp = frame_values(row, data.clip)
        if frame not in frames:
            raise ValueError("Prediction frame was not declared processed")
        if frame in reviewed and abs(reviewed[frame] - timestamp) > 0.001:
            raise ValueError("Prediction timestamp disagrees with annotated frame")
        if frame in timestamps and timestamp != timestamps[frame]:
            raise ValueError("Inconsistent prediction timestamps within a frame")
        timestamps[frame] = timestamp
        identity = row.get("track_id")
        if family != "detections":
            if not identity or integer(identity) < 1 or (frame, identity) in seen:
                raise ValueError("Invalid or duplicate predicted Track ID")
            seen.add((frame, identity))
        confidence = number(row["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("Confidence must be in [0,1]")
        if row.get("class_name", "person") != "person":
            raise ValueError("Expected person-only detection artifact")
        if "class_id" in row:
            integer(row["class_id"])
        for name in ("pixel_x", "pixel_y"):
            if name in row:
                number(row[name])
        if "inside_pitch" in row:
            boolean(row["inside_pitch"])
        for column, expected in (
            ("frame_width", data.clip.width),
            ("frame_height", data.clip.height),
        ):
            if column in row and integer(row[column]) != expected:
                raise ValueError("Prediction dimensions do not match the video")
        pitch = optional_pitch(row)
        if family == "coordinates" and pitch is None:
            raise ValueError("Mapped coordinates cannot be empty")
        return Observation(
            frame,
            timestamp,
            box_values(row, data.clip),
            identity,
            confidence=confidence,
            pitch=pitch,
        )

    result = read_rows(path, columns, parse, config.max_rows_per_file, "prediction")
    ordered = sorted(timestamps.items())
    if any(a[1] >= b[1] for a, b in zip(ordered, ordered[1:], strict=False)):
        raise InputError("Prediction timestamps must increase across frames")
    return result


def load_teams(path: Path, data: ClipData, config: EvaluationConfig) -> dict[str, str]:
    known = {r.track_id for r in data.tracks or []}
    labels = {}

    def parse(row):
        identity, label = row["track_id"], row["automatic_team"]
        if identity in labels or identity not in known:
            raise ValueError("Duplicate or unknown automatic team Track ID")
        if label not in {"team_a", "team_b", "unknown"}:
            raise ValueError("Invalid automatic team label")
        confidence = number(row["automatic_confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("Invalid automatic team confidence")
        labels[identity] = label  # Explicitly never consume manual/effective_team.

    read_rows(
        path,
        {"track_id", "automatic_team", "automatic_confidence"},
        parse,
        config.max_rows_per_file,
        "prediction",
    )
    return labels


def verify_video(path: Path, clip: Clip) -> None:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise InputError(f"Cannot open declared validation video: {clip.clip_id}")
        actual = (
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        if (
            actual != (clip.width, clip.height)
            or count != clip.frame_count
            or abs(fps - clip.fps) > 0.01
        ):
            raise InputError(f"Video metadata differs from manifest: {clip.clip_id}")
    finally:
        capture.release()


def validate_calibration(path: Path, clip: Clip) -> None:
    from app.cv.homography import validate_homography

    record = CalibrationSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        record.video_sha256 != clip.video.sha256
        or record.pitch_length_metres != clip.pitch_length_metres
        or record.pitch_width_metres != clip.pitch_width_metres
        or clip.pitch_length_metres is None
        or not 0 <= record.frame_number < clip.frame_count
    ):
        raise InputError("Saved calibration does not match the evaluated video/pitch")
    validate_homography(record.matrix)


def cleaned_diagnostics(
    path: Path, data: ClipData, frames: set[int], config: EvaluationConfig
) -> tuple[int, int]:
    from app.services.trajectory_artifacts import COLUMNS

    seen = set()

    def parse(row):
        frame, _ = frame_values(row, data.clip)
        identity = integer(row["track_id"])
        if frame not in frames or identity < 1 or (frame, identity) in seen:
            raise ValueError("Invalid or duplicate cleaned row identity")
        seen.add((frame, identity))
        box_values(row, data.clip)
        for name in ("confidence", "pixel_x", "pixel_y", "raw_pitch_x", "raw_pitch_y"):
            number(row[name])
        if not 0 <= number(row["confidence"]) <= 1:
            raise ValueError("Invalid cleaned-row confidence")
        usable = boolean(row["usable"])
        boolean(row["inside_pitch"])
        if boolean(row["is_interpolated"]):
            raise ValueError("Unexpected interpolation in Phase 10 observations")
        point = optional_pitch(
            {"pitch_x": row["clean_pitch_x"], "pitch_y": row["clean_pitch_y"]}
        )
        if usable != (point is not None):
            raise ValueError("Cleaned position availability disagrees with usable flag")
        return usable

    rows = read_rows(path, set(COLUMNS), parse, config.max_rows_per_file, "prediction")
    return len(rows), sum(rows)


def load_dataset(
    dataset_path: Path,
    predictions_path: Path | None,
    config: EvaluationConfig,
    *,
    allow_synthetic: bool = False,
) -> tuple[Dataset, list[ClipData], Predictions | None, dict]:
    dataset = Dataset.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    if dataset.provenance == "synthetic" and not allow_synthetic:
        raise InputError(
            "Synthetic data requires --allow-synthetic; it is never real model accuracy"
        )
    predictions = None
    prediction_map = {}
    if predictions_path:
        predictions = Predictions.model_validate_json(
            predictions_path.read_text(encoding="utf-8")
        )
        if predictions.dataset_sha256 != sha256(dataset_path):
            raise InputError(
                "Prediction manifest belongs to a different dataset version"
            )
        if (dataset.provenance == "synthetic") != (predictions.source == "synthetic"):
            raise InputError(
                "Synthetic and empirical data/predictions must never be mixed"
            )
        validate_pipeline_snapshot(predictions.pipeline_config)
        prediction_map = {c.clip_id: c for c in predictions.clips}
        if len(prediction_map) != len(predictions.clips) or not set(
            prediction_map
        ).issubset({c.clip_id for c in dataset.clips}):
            raise InputError("Duplicate or unknown prediction clip IDs")
    loaded, hashes = [], {str(dataset_path.resolve()): sha256(dataset_path)}
    if predictions_path:
        hashes[str(predictions_path.resolve())] = sha256(predictions_path)
        if predictions.model_weights:
            path = checked_file(predictions_path.parent, predictions.model_weights)
            hashes[str(path)] = predictions.model_weights.sha256
    for clip in dataset.clips:
        references = [clip.video, clip.frames, clip.annotations, clip.landmarks]
        for ref in filter(None, references):
            path = checked_file(dataset_path.parent, ref)
            hashes[str(path)] = ref.sha256
        verify_video(checked_file(dataset_path.parent, clip.video), clip)
        data = load_annotations(dataset_path.parent, clip, config)
        prediction = prediction_map.get(clip.clip_id)
        if prediction:
            if (
                prediction.video_sha256 != clip.video.sha256
                or prediction.pipeline_config_sha256
                != digest_json(predictions.pipeline_config)
            ):
                raise InputError(
                    f"Stale video/configuration provenance: {clip.clip_id}"
                )
            frames = set(prediction.processed_frames)
            if not {f.number for f in data.frames}.issubset(frames) or any(
                f < 0 or f >= clip.frame_count for f in frames
            ):
                raise InputError(
                    "Every reviewed frame must have been processed, "
                    "including empty frames"
                )
            if prediction.calibration:
                path = checked_file(predictions_path.parent, prediction.calibration)
                hashes[str(path)] = prediction.calibration.sha256
                validate_calibration(path, clip)
            for family in ("detections", "tracks", "coordinates"):
                ref = getattr(prediction, family)
                if ref:
                    path = checked_file(predictions_path.parent, ref)
                    hashes[str(path)] = ref.sha256
                    setattr(
                        data, family, load_boxes(path, data, frames, family, config)
                    )
            if prediction.automatic_teams:
                path = checked_file(predictions_path.parent, prediction.automatic_teams)
                hashes[str(path)] = prediction.automatic_teams.sha256
                data.automatic_teams = load_teams(path, data, config)
            if prediction.cleaned:
                path = checked_file(predictions_path.parent, prediction.cleaned)
                hashes[str(path)] = prediction.cleaned.sha256
                data.cleaned_rows, data.usable_cleaned_rows = cleaned_diagnostics(
                    path, data, frames, config
                )
            data.prediction = prediction
        loaded.append(data)
    return dataset, loaded, predictions, hashes


def recheck(hashes: dict[str, str]) -> None:
    for name, expected in hashes.items():
        path = Path(name)
        if not path.is_file() or sha256(path) != expected:
            raise InputError(
                "An input changed during evaluation; output was not published"
            )
