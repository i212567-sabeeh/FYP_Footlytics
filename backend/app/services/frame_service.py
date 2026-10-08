"""Seek/decode one calibration frame using the existing isolated video helper."""

import base64
import json
import logging
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.models.media import MatchVideo
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationFrame:
    video_id: int
    frame_number: int
    timestamp_seconds: float
    width: int
    height: int
    jpeg: bytes


def extract_frame(
    video: MatchVideo,
    timestamp_seconds: float,
    settings: Settings,
    *,
    frame_number: int | None = None,
) -> CalibrationFrame:
    # Review uses an exact frame index. Existing calibration timestamp calls keep
    # their original behavior and share the same isolated decoder and timeout.
    if frame_number is not None and (type(frame_number) is not int or frame_number < 0):
        raise DomainError(422, "Choose a non-negative frame number.")
    if (
        not math.isfinite(timestamp_seconds)
        or not 0 <= timestamp_seconds < video.duration_seconds
    ):
        raise DomainError(
            422,
            "Choose a timestamp from zero up to, but not including, "
            "the video duration.",
        )
    path = StorageService(settings).resolve(video.relative_storage_path)
    try:
        if not path.is_file():
            raise DomainError(404, "The stored source video is no longer available.")
        if path.stat().st_size != video.file_size_bytes:
            raise DomainError(409, "The stored source video changed. Upload it again.")
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).with_name("video_decode.py")),
                str(path),
                str(timestamp_seconds),
                *(
                    ["--frame-number", str(frame_number)]
                    if frame_number is not None
                    else []
                ),
            ],
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            timeout=settings.video_inspection_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise DomainError(
            422,
            "Frame extraction timed out. Choose an earlier timestamp or another video.",
        ) from None
    except UnicodeError:
        raise DomainError(
            422, "The requested video frame could not be decoded."
        ) from None
    except OSError:
        logger.exception(
            "Calibration frame extraction could not access the video decoder"
        )
        raise DomainError(503, "Frame extraction is temporarily unavailable.") from None
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError
        if data.get("error") == "unavailable":
            raise DomainError(503, "The server video decoder is unavailable.")
        if result.returncode != 0 or "error" in data:
            raise ValueError
        width, height = data["width"], data["height"]
        number, timestamp = data["frame_number"], data["timestamp_seconds"]
        if (
            type(number) is not int
            or number < 0
            or (frame_number is not None and number != frame_number)
            or not math.isfinite(timestamp)
            or not 0 <= timestamp < video.duration_seconds
            or sorted((width, height)) != sorted((video.width, video.height))
        ):
            raise ValueError
        jpeg = base64.b64decode(data["jpeg_base64"], validate=True)
        if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            raise ValueError
        return CalibrationFrame(video.id, number, timestamp, width, height, jpeg)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise DomainError(
            422,
            "The requested video frame could not be decoded. Choose another timestamp.",
        ) from None
