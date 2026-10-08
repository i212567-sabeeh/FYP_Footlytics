"""Validate saved coordinates and externally sort without holding a match in RAM."""

import csv
import heapq
import json
import math
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import astuple, dataclass
from pathlib import Path

from app.cv.player_position import bottom_center, inside_pitch
from app.schemas.coordinates import CoordinateSummary
from app.services.coordinate_artifacts import COLUMNS

SORT_CHUNK_ROWS = 4096
MERGE_FAN_IN = 16


class TrajectoryError(Exception):
    """Only curated messages may be returned through processing jobs."""


@dataclass(frozen=True)
class CoordinateObservation:
    source_row: int
    frame: int
    timestamp: float
    track_id: int
    box: tuple[float, ...]
    confidence: float
    pixel: tuple[float, float]
    pitch: tuple[float, float]
    inside_pitch: bool


def _key(row: CoordinateObservation) -> tuple[int, float, int, int]:
    return row.track_id, row.timestamp, row.frame, row.source_row


def _read(
    path: Path,
    summary: CoordinateSummary,
    decoded_frames: int,
    frame_stride: int,
    duration: float,
) -> Iterator[CoordinateObservation]:
    count = inside = 0
    first = last = None
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ValueError("Header changed")
            for count, row in enumerate(reader, 1):
                if len(row) != len(COLUMNS) or any(v is None for v in row.values()):
                    raise ValueError("Malformed row")
                frame, track_id = int(row["frame_number"]), int(row["track_id"])
                timestamp, confidence = (
                    float(row["timestamp_seconds"]),
                    float(row["confidence"]),
                )
                box = tuple(float(row[k]) for k in ("x1", "y1", "x2", "y2"))
                pixel = (float(row["pixel_x"]), float(row["pixel_y"]))
                pitch = (float(row["pitch_x"]), float(row["pitch_y"]))
                flag = row["inside_pitch"]
                if (
                    not 0 <= frame < decoded_frames
                    or frame % frame_stride
                    or not 0 < track_id <= 2**63 - 1
                    or not all(
                        math.isfinite(v)
                        for v in (timestamp, confidence, *box, *pixel, *pitch)
                    )
                    or timestamp >= duration
                    or not 0 <= confidence <= 1
                    or flag not in ("true", "false")
                    or any(
                        not math.isclose(a, b, abs_tol=1e-6)
                        for a, b in zip(bottom_center(box), pixel, strict=True)
                    )
                    or (flag == "true")
                    != inside_pitch(
                        *pitch, summary.pitch_length_metres, summary.pitch_width_metres
                    )
                    or count > summary.valid_mapped_rows
                ):
                    raise ValueError("Invalid coordinate observation")
                inside += flag == "true"
                first = frame if first is None else min(first, frame)
                last = frame if last is None else max(last, frame)
                yield CoordinateObservation(
                    count,
                    frame,
                    timestamp,
                    track_id,
                    box,
                    confidence,
                    pixel,
                    pitch,
                    flag == "true",
                )
        if (
            count != summary.valid_mapped_rows
            or inside != summary.inside_pitch_rows
            or count - inside != summary.outside_pitch_rows
            or (first, last) != (summary.first_frame, summary.last_frame)
        ):
            raise ValueError("Coordinate summary mismatch")
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        raise TrajectoryError(
            "The coordinate CSV is invalid or incomplete. Map coordinates again."
        ) from None


def _write_run(path: Path, rows: Iterator[CoordinateObservation]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(astuple(row), allow_nan=False) + "\n")


def _decode(stream) -> Iterator[CoordinateObservation]:
    for line in stream:
        values = json.loads(line)
        values[4], values[6], values[7] = (
            tuple(values[4]),
            tuple(values[6]),
            tuple(values[7]),
        )
        yield CoordinateObservation(*values)


def _merge(paths: list[Path]) -> Iterator[CoordinateObservation]:
    with ExitStack() as stack:
        streams = [stack.enter_context(p.open(encoding="utf-8")) for p in paths]
        yield from heapq.merge(*(_decode(s) for s in streams), key=_key)


def ordered_coordinates(
    path: Path,
    summary: CoordinateSummary,
    decoded_frames: int,
    frame_stride: int,
    duration: float,
    workspace: Path,
    progress: Callable[[int, int], None],
) -> Iterator[CoordinateObservation]:
    """Bound row memory and open files, even for unsorted, interleaved tracks.

    Workspace is an attempt-owned TemporaryDirectory managed by the caller.
    Input order breaks exact ties deterministically; no original row is discarded.
    """
    runs: list[Path] = []
    chunk: list[CoordinateObservation] = []

    def spill() -> None:
        target = workspace / f"run-0-{len(runs)}.jsonl"
        chunk.sort(key=_key)
        _write_run(target, iter(chunk))
        runs.append(target)
        chunk.clear()

    rows = _read(path, summary, decoded_frames, frame_stride, duration)
    try:
        for row in rows:
            chunk.append(row)
            if len(chunk) == SORT_CHUNK_ROWS:
                spill()
                progress(row.source_row, summary.valid_mapped_rows)
        if chunk:
            spill()
        progress(summary.valid_mapped_rows, summary.valid_mapped_rows)
    finally:
        rows.close()
    generation = 0
    while len(runs) > MERGE_FAN_IN:
        generation += 1
        merged = []
        for start in range(0, len(runs), MERGE_FAN_IN):
            group = runs[start : start + MERGE_FAN_IN]
            target = workspace / f"run-{generation}-{start}.jsonl"
            iterator = _merge(group)
            try:
                _write_run(target, iterator)
            finally:
                iterator.close()
            merged.append(target)
            for original in group:
                original.unlink()
        runs = merged
    yield from _merge(runs)
