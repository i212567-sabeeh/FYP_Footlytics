"""Bounded external regrouping: Phase 10 is track/time ordered, tactics is by frame."""

import heapq
import json
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack
from dataclasses import astuple
from pathlib import Path

from app.analytics.trajectory_rows import CleanObservation

SORT_CHUNK_ROWS = 4096
MERGE_FAN_IN = 16


def _key(row: CleanObservation):
    return row.frame, row.track_id


def _write(path: Path, rows: Iterable[CleanObservation]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(astuple(row), allow_nan=False) + "\n")


def _decode(stream) -> Iterator[CleanObservation]:
    for line in stream:
        values = json.loads(line)
        values[4] = tuple(values[4])
        yield CleanObservation(*values)


def _merge(paths: list[Path]) -> Iterator[CleanObservation]:
    with ExitStack() as stack:
        streams = [stack.enter_context(p.open(encoding="utf-8")) for p in paths]
        yield from heapq.merge(*(_decode(s) for s in streams), key=_key)


def ordered_snapshots(
    rows: Iterable[CleanObservation],
    workspace: Path,
    total: int,
    progress: Callable[[int, int], None],
) -> Iterator[CleanObservation]:
    """Disk runs cap row memory and merge file handles; caller owns scratch cleanup."""
    runs, chunk = [], []

    def spill():
        target = workspace / f"run-0-{len(runs)}.jsonl"
        chunk.sort(key=_key)
        _write(target, chunk)
        runs.append(target)
        chunk.clear()

    for count, row in enumerate(rows, 1):
        if row.clean is not None:
            chunk.append(row)
        if len(chunk) == SORT_CHUNK_ROWS:
            spill()
        if count % SORT_CHUNK_ROWS == 0:
            progress(count, total)
    if chunk:
        spill()
    progress(total, total)
    generation = 0
    while len(runs) > MERGE_FAN_IN:
        generation += 1
        merged = []
        for start in range(0, len(runs), MERGE_FAN_IN):
            group = runs[start : start + MERGE_FAN_IN]
            target = workspace / f"run-{generation}-{start}.jsonl"
            iterator = _merge(group)
            try:
                _write(target, iterator)
            finally:
                iterator.close()
            merged.append(target)
            for original in group:
                original.unlink()
        runs = merged
    yield from _merge(runs)
