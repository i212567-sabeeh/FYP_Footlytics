"""Bounded metadata extraction plus an actual frame decode; no video analytics."""

import json
import logging
import math
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from app.core.config import Settings
from app.services.domain_common import DomainError
from app.services.video_decode import valid_metadata

logger = logging.getLogger(__name__)
INVALID_VIDEO = "The file is not a readable supported video. Choose another MP4 or MOV."
FALLBACK_WARNING = (
    "ffprobe is unavailable. Basic metadata comes from OpenCV; duration is estimated "
    "from frame count and FPS, and codec/container details are unavailable."
)


@dataclass(frozen=True)
class VideoMetadata:
    container_format: str | None
    codec: str | None
    width: int
    height: int
    fps: float
    duration_seconds: float
    frame_count: int | None
    warning_message: str | None = None


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Invalid number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite number")
    return number


def _integer(value: object) -> int:
    number = _number(value)
    if not number.is_integer() or number <= 0:
        raise ValueError("Invalid integer")
    return int(number)


def _optional_count(value: object) -> int | None:
    if value is None or value == "N/A":
        return None
    return _integer(value)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError("Invalid metadata text")
    return value


def _rate(stream: dict) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = stream.get(key)
        if isinstance(value, str):
            try:
                rate = float(Fraction(value))
            except (ValueError, ZeroDivisionError, OverflowError):
                continue
            if math.isfinite(rate) and rate > 0:
                return rate
    raise ValueError("Missing frame rate")


def _probe_metadata(data: object) -> VideoMetadata:
    if not isinstance(data, dict):
        raise ValueError("Invalid probe response")
    streams = data.get("streams")
    format_info = data.get("format", {})
    if (
        not isinstance(streams, list)
        or not streams
        or not isinstance(streams[0], dict)
        or not isinstance(format_info, dict)
    ):
        raise ValueError("Missing video stream")
    stream = streams[0]
    if stream.get("codec_type") != "video":
        raise ValueError("Missing video stream")
    duration = stream.get("duration")
    if duration is None or duration == "N/A":
        duration = format_info.get("duration")
    return VideoMetadata(
        container_format=_text(format_info.get("format_name")),
        codec=_text(stream.get("codec_name")),
        width=_integer(stream.get("width")),
        height=_integer(stream.get("height")),
        fps=_rate(stream),
        duration_seconds=_number(duration),
        frame_count=_optional_count(stream.get("nb_frames")),
    )


def _run_probe(path: Path, settings: Settings) -> VideoMetadata | None:
    try:
        result = subprocess.run(
            [
                settings.ffprobe_path,
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-format_whitelist",
                "mov",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,avg_frame_rate,"
                "r_frame_rate,duration,nb_frames:format=format_name,duration",
                "-of",
                "json",
                "-i",
                str(path),
            ],
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            timeout=settings.video_inspection_timeout_seconds,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        raise DomainError(
            422, "Video inspection timed out. Choose another video."
        ) from None
    except UnicodeError:
        raise DomainError(422, INVALID_VIDEO) from None
    except OSError:
        logger.exception("Could not start ffprobe")
        raise DomainError(503, "Video inspection is temporarily unavailable.") from None
    try:
        if result.returncode != 0:
            raise ValueError("Probe rejected the video")
        return _probe_metadata(json.loads(result.stdout))
    except (ValueError, TypeError, OverflowError):
        raise DomainError(422, INVALID_VIDEO) from None


def _decode(path: Path, settings: Settings) -> dict:
    helper = Path(__file__).with_name("video_decode.py")
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(helper), str(path)],
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
            422, "Video decoding timed out. Choose another video."
        ) from None
    except UnicodeError:
        raise DomainError(422, INVALID_VIDEO) from None
    except OSError:
        logger.exception("Could not start isolated video decoder")
        raise DomainError(503, "Video decoding is temporarily unavailable.") from None
    try:
        decoded = json.loads(result.stdout)
        if not isinstance(decoded, dict):
            raise ValueError("Invalid decoder response")
        if decoded.get("error") == "unavailable":
            raise DomainError(503, "The server video decoder is unavailable.")
        if result.returncode != 0 or "error" in decoded:
            raise ValueError("Decoder rejected the video")
        return decoded
    except (ValueError, TypeError):
        raise DomainError(422, INVALID_VIDEO) from None


def _check_mov_header(path: Path) -> None:
    """Reject renamed foreign containers before using fallback demuxing.

    MP4 and QuickTime MOV are atom-based containers. This is only a bounded format
    check; the independent decoder must still prove that a real frame is readable.
    Older QuickTime files may start with moov/mdat instead of the newer ftyp atom.
    """
    try:
        with path.open("rb") as source:
            header = source.read(16)
        size = int.from_bytes(header[:4], "big")
        kind = header[4:8]
        if len(header) < 8 or kind not in {
            b"ftyp",
            b"moov",
            b"mdat",
            b"wide",
            b"free",
            b"skip",
            b"pnot",
        }:
            raise DomainError(422, INVALID_VIDEO)
        if size == 1:
            if len(header) < 16 or int.from_bytes(header[8:16], "big") < 16:
                raise DomainError(422, INVALID_VIDEO)
        elif size != 0 and size < 8:
            raise DomainError(422, INVALID_VIDEO)
    except OSError:
        logger.exception("Could not read video container header")
        raise DomainError(500, "The stored video could not be read.") from None


def inspect_video(path: Path, settings: Settings) -> VideoMetadata:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            raise DomainError(422, "The video is empty or no longer available.")
    except OSError:
        logger.exception("Could not read uploaded video")
        raise DomainError(500, "The stored video could not be read.") from None
    metadata = _run_probe(path, settings)
    if metadata is None:
        _check_mov_header(path)
    if metadata is not None and not valid_metadata(
        metadata.width, metadata.height, metadata.fps, metadata.duration_seconds
    ):
        raise DomainError(422, "Video dimensions, FPS or duration are invalid.")
    decoded = _decode(path, settings)
    try:
        if metadata is None:
            count = _integer(decoded.get("frame_count"))
            fps = _number(decoded.get("fps"))
            metadata = VideoMetadata(
                container_format=None,
                codec=None,
                width=_integer(decoded.get("width")),
                height=_integer(decoded.get("height")),
                fps=fps,
                duration_seconds=count / fps,
                frame_count=count,
                warning_message=FALLBACK_WARNING,
            )
        if not valid_metadata(
            metadata.width, metadata.height, metadata.fps, metadata.duration_seconds
        ):
            raise ValueError("Invalid video metadata")
        # A rotated phone video may swap displayed width/height when decoded.
        if sorted((metadata.width, metadata.height)) != sorted(
            (_integer(decoded.get("width")), _integer(decoded.get("height")))
        ):
            raise ValueError("Decoded dimensions disagree with metadata")
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        raise DomainError(
            422, "Video dimensions, FPS or duration are invalid."
        ) from None
    logger.info("Video metadata extracted; decoder readability verified")
    return metadata
