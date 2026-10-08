"""Draw saved observations on one decoded frame; no detector or tracker runs."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class PreviewBox:
    bbox: tuple[float, float, float, float]
    confidence: float
    track_id: int | None = None


def annotate_frame(jpeg: bytes, boxes: list[PreviewBox]) -> bytes:
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Preview image could not be decoded")
    height, width = image.shape[:2]
    scale = max(0.4, min(1.0, width / 1600))
    thickness = max(1, round(width / 800))
    # One neutral overlay color for all people: colors never imply team membership.
    color = (80, 220, 120)
    for box in boxes:
        x1, y1, x2, y2 = map(round, box.bbox)
        x1, x2 = min(x1, width - 1), min(x2, width - 1)
        y1, y2 = min(y1, height - 1), min(y2, height - 1)
        label = (
            f"ID {box.track_id}"
            if box.track_id is not None
            else f"person {box.confidence:.0%}"
        )
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1
        )
        text_y = min(height - baseline - 1, max(text_height + 2, y1 - 4))
        text_x = max(0, min(x1, width - text_width - 2))
        cv2.rectangle(
            image,
            (text_x, max(0, text_y - text_height - 2)),
            (
                min(width - 1, text_x + text_width + 2),
                min(height - 1, text_y + baseline),
            ),
            (20, 25, 30),
            -1,
        )
        cv2.putText(
            image,
            label,
            (text_x + 1, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            1,
            cv2.LINE_AA,
        )
    encoded, result = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not encoded:
        raise ValueError("Preview image could not be encoded")
    return result.tobytes()
