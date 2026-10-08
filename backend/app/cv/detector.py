"""Pretrained person candidates, isolated from Ultralytics result objects."""

import logging
import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from app.core.config import PROJECT_ROOT, Settings

if TYPE_CHECKING:
    from ultralytics import YOLO

logger = logging.getLogger(__name__)
Image = NDArray[np.uint8]


class DetectionError(Exception):
    """Only curated messages from this exception may be stored in job responses."""


@dataclass(frozen=True)
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str

    @property
    def bottom_centre(self) -> tuple[float, float]:
        x1, _, x2, y2 = self.bbox
        return ((x1 + x2) / 2, y2)


def is_reported(confidence: float, threshold: float) -> bool:
    """Reported detections meet YOLO_CONFIDENCE and drive counts and overlays.

    Lower stored boxes are ByteTrack low-score candidates. Settings keep
    TRACK_HIGH_THRESH >= YOLO_CONFIDENCE, so they may extend a track through
    an occlusion but can never start one.
    """
    return confidence >= threshold


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, frame: Image) -> list[Detection]:
        """Return candidates in the input frame's original pixel coordinates."""


def select_device(requested: str, cuda_available: bool) -> str:
    if requested == "auto":
        return "cuda:0" if cuda_available else "cpu"
    if requested.startswith("cuda") and not cuda_available:
        raise DetectionError("CUDA is unavailable. Set DEVICE=auto or DEVICE=cpu.")
    return "cuda:0" if requested == "cuda" else requested


def _load_model(settings: Settings) -> "YOLO":
    # A bare pretrained model name downloads into ignored storage, independent of
    # worker cwd. Explicit local .pt paths remain an administrator's configuration.
    directory = settings.storage_dir / "models"
    directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(directory / ".ultralytics"))
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    from ultralytics import YOLO

    path = Path(settings.yolo_model)
    path = directory / path if path.parent == Path(".") else PROJECT_ROOT / path
    return YOLO(str(path), task="detect")


class YoloPlayerDetector(BaseDetector):
    def __init__(self, settings: Settings):
        # Also keep ByteTrack's low-score candidates. Boxes above YOLO_CONFIDENCE
        # are unchanged: NMS only lets a higher-score box suppress a lower one.
        self.candidate_confidence = settings.detection_candidate_confidence
        self.image_size = settings.yolo_image_size
        self.model_name = Path(settings.yolo_model).name
        try:
            import torch

            self.device = select_device(settings.device, torch.cuda.is_available())
            logger.info("YOLO detection selected device %s", self.device)
            self._model = _load_model(settings)
            if self._model.task != "detect":
                raise DetectionError("Configure pretrained object-detection weights.")
            names = self._model.names
            people = [int(key) for key, value in names.items() if value == "person"]
            if len(people) != 1:
                raise DetectionError(
                    "The configured model must contain a person class."
                )
            self.person_class_id = people[0]
        except DetectionError:
            raise
        except Exception as error:
            raise DetectionError(
                "The YOLO model could not be loaded. Check installed dependencies, "
                "weights and download access, then retry."
            ) from error

    def detect(self, frame: Image) -> list[Detection]:
        if (
            frame.ndim != 3
            or frame.shape[2] != 3
            or not frame.size
            or frame.dtype != np.uint8
        ):
            raise DetectionError("Detection requires a nonempty BGR video frame.")
        height, width = frame.shape[:2]
        try:
            results = self._model.predict(
                source=frame,
                classes=[self.person_class_id],
                conf=self.candidate_confidence,
                imgsz=self.image_size,
                device=self.device,
                verbose=False,
                save=False,
            )
            if len(results) != 1 or results[0].boxes is None:
                raise ValueError("Expected one detection result with boxes")
            boxes = results[0].boxes.cpu().numpy()
            detections = []
            for xyxy, score, label in zip(
                boxes.xyxy, boxes.conf, boxes.cls, strict=True
            ):
                score, label = float(score), float(label)
                if not math.isfinite(label) or not label.is_integer():
                    raise ValueError("Invalid class ID")
                if int(label) != self.person_class_id:
                    continue
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid confidence")
                if score < self.candidate_confidence:
                    continue
                if len(xyxy) != 4 or not np.isfinite(xyxy).all():
                    raise ValueError("Invalid bounding box")
                # Ultralytics xyxy is already in original-image pixels. Clip only
                # at image edges; never rescale using the inference tensor size.
                x1, y1, x2, y2 = map(float, xyxy)
                x1, x2 = max(0.0, x1), min(float(width), x2)
                y1, y2 = max(0.0, y1), min(float(height), y2)
                if x2 <= x1 or y2 <= y1:
                    raise ValueError("Empty bounding box")
                detections.append(
                    Detection((x1, y1, x2, y2), score, int(label), "person")
                )
            return detections
        except Exception as error:
            raise DetectionError(
                "YOLO detection failed for a video frame. Check worker logs and retry."
            ) from error
