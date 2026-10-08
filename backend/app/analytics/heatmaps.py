"""Observed residence time at interval starts, on the Match's own pitch grid."""

from collections.abc import Iterator

from app.schemas.player_analytics import HeatmapCell


class OccupancyGrid:
    def __init__(self, length: float, width: float, bins_x: int, bins_y: int):
        self.length, self.width = length, width
        self.bins_x, self.bins_y = bins_x, bins_y
        self.seconds: dict[tuple[int, int], float] = {}

    def add(self, point: tuple[float, float], dt: float) -> None:
        # Inputs are finite in-pitch cleaned points and validated positive dt.
        # A point exactly on the maximum boundary belongs to the final cell.
        # Keep Phase 9/10's micrometre boundary tolerance. Clamp only the cell
        # index; never change the coordinates used to calculate movement.
        x = max(0, min(self.bins_x - 1, int(point[0] / self.length * self.bins_x)))
        y = max(0, min(self.bins_y - 1, int(point[1] / self.width * self.bins_y)))
        self.seconds[x, y] = self.seconds.get((x, y), 0.0) + dt

    def cells(self, track_id: int, duration: float) -> Iterator[HeatmapCell]:
        for (x, y), seconds in sorted(self.seconds.items()):
            yield HeatmapCell(
                track_id=track_id,
                x_bin=x,
                y_bin=y,
                x_min=x * self.length / self.bins_x,
                x_max=(x + 1) * self.length / self.bins_x,
                y_min=y * self.width / self.bins_y,
                y_max=(y + 1) * self.width / self.bins_y,
                occupancy_seconds=seconds,
                occupancy_fraction=min(1.0, seconds / duration),
            )
