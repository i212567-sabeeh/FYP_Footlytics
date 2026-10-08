"""Small isolated OpenCV reader; native decoder failures stay outside the API."""

import base64
import json
import math
import os
import sys

# Broad input limits, not football measurements. Check these before allocating a
# decoded frame; they allow up to 8K footage and long recorded events.
MAX_VIDEO_PIXELS = 8192 * 4320
MAX_VIDEO_DIMENSION = 16384
MAX_VIDEO_DURATION = 24 * 60 * 60
MAX_VIDEO_FPS = 240


def valid_metadata(width: int, height: int, fps: float, duration: float) -> bool:
    return (
        1 <= width <= MAX_VIDEO_DIMENSION
        and 1 <= height <= MAX_VIDEO_DIMENSION
        and width * height <= MAX_VIDEO_PIXELS
        and math.isfinite(fps)
        and 0 < fps <= MAX_VIDEO_FPS
        and math.isfinite(duration)
        and 0 < duration <= MAX_VIDEO_DURATION
    )


def decode_first_frame(
    path: str,
    *,
    timestamp_seconds: float | None = None,
    frame_number: int | None = None,
) -> dict:
    """Decode one frame; optional seeking/JPEG output serves pitch calibration."""
    # Only the MP4/MOV demuxer and local file access are needed. An uploaded
    # playlist must not make the decoder fetch network URLs or another format.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "format_whitelist;mov|protocol_whitelist;file"
    )
    os.environ["OPENCV_FFMPEG_THREADS"] = "1"
    try:
        import cv2
    except ImportError:
        return {"error": "unavailable"}

    capture = cv2.VideoCapture()
    try:
        capture.open(path, cv2.CAP_FFMPEG)
        if not capture.isOpened():
            return {"error": "unreadable"}
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count_value = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_count = (
            int(frame_count_value)
            if math.isfinite(frame_count_value) and frame_count_value > 0
            else None
        )
        # Unknown frame counts do not prevent a decode when ffprobe supplies the
        # duration. The caller rejects them when only fallback metadata exists.
        duration = frame_count / fps if frame_count and fps > 0 else 1.0
        if not valid_metadata(width, height, fps, duration):
            return {"error": "invalid_metadata"}
        if frame_number is not None:
            if type(frame_number) is not int or frame_number < 0:
                return {"error": "invalid_frame"}
            if frame_number > 0 and not capture.set(
                cv2.CAP_PROP_POS_FRAMES, frame_number
            ):
                return {"error": "seek_failed"}
        elif timestamp_seconds is not None:
            if not math.isfinite(timestamp_seconds) or timestamp_seconds < 0:
                return {"error": "invalid_timestamp"}
            if timestamp_seconds > 0 and not capture.set(
                cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000
            ):
                return {"error": "seek_failed"}
        readable, frame = capture.read()
        if not readable or frame is None or frame.size == 0:
            return {"error": "unreadable"}
        result = {
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "fps": fps,
            "frame_count": frame_count,
        }
        if timestamp_seconds is not None or frame_number is not None:
            position = capture.get(cv2.CAP_PROP_POS_FRAMES)
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if (
                not math.isfinite(position)
                or position < 1
                or not math.isfinite(timestamp)
                or timestamp < 0
                or (
                    frame_number is not None
                    and int(round(position)) - 1 != frame_number
                )
            ):
                return {"error": "frame_metadata_unavailable"}
            encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not encoded:
                return {"error": "encoding_failed"}
            result.update(
                frame_number=int(round(position)) - 1,
                timestamp_seconds=timestamp,
                jpeg_base64=base64.b64encode(jpeg.tobytes()).decode("ascii"),
            )
        return result
    except (cv2.error, ValueError, OverflowError):
        return {"error": "unreadable"}
    finally:
        capture.release()


if __name__ == "__main__":
    timestamp = float(sys.argv[2]) if len(sys.argv) > 2 else None
    print(
        json.dumps(
            decode_first_frame(
                sys.argv[1],
                timestamp_seconds=timestamp,
                frame_number=int(sys.argv[4])
                if len(sys.argv) == 5 and sys.argv[3] == "--frame-number"
                else None,
            ),
            allow_nan=False,
        )
    )
