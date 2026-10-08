import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.services.domain_common import DomainError
from app.services.video_inspection import FALLBACK_WARNING, inspect_video


@pytest.fixture(params=[".mp4", ".mov"])
def tiny_video(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    """Generated 48x32 test patterns, six frames; no football or personal footage."""
    path = tmp_path / f"synthetic{request.param}"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 12, (48, 32))
    assert writer.isOpened(), "OpenCV must support MP4/MOV fixture generation"
    try:
        for index in range(6):
            frame = np.zeros((32, 48, 3), dtype=np.uint8)
            frame[:, :, index % 3] = 30 + index * 30
            writer.write(frame)
    finally:
        writer.release()
    assert path.stat().st_size > 0
    return path


@pytest.fixture
def inspection_settings() -> Settings:
    return Settings(_env_file=None, ffprobe_path="definitely-missing-test-ffprobe")


def test_real_mp4_mov_fallback_extracts_metadata_and_decodes(
    tiny_video, inspection_settings
):
    metadata = inspect_video(tiny_video, inspection_settings)
    assert (metadata.width, metadata.height) == (48, 32)
    assert metadata.fps == pytest.approx(12, abs=0.01)
    assert metadata.frame_count == 6
    assert metadata.duration_seconds == pytest.approx(0.5, abs=0.02)
    assert metadata.container_format is None
    assert metadata.codec is None
    assert metadata.warning_message == FALLBACK_WARNING


def probe_output(**updates) -> subprocess.CompletedProcess:
    stream = {
        "codec_type": "video",
        "codec_name": "mpeg4",
        "width": 48,
        "height": 32,
        "avg_frame_rate": "12/1",
        "r_frame_rate": "12/1",
        "duration": "0.500000",
        "nb_frames": "6",
    }
    stream.update(updates)
    return subprocess.CompletedProcess(
        [],
        0,
        json.dumps({"streams": [stream], "format": {"format_name": "mov,mp4"}}),
    )


def test_probe_metadata_still_requires_actual_frame_decode(
    tiny_video, inspection_settings
):
    original_run = subprocess.run
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return probe_output() if len(calls) == 1 else original_run(args, **kwargs)

    with patch("app.services.video_inspection.subprocess.run", side_effect=run):
        metadata = inspect_video(tiny_video, inspection_settings)
    assert metadata.codec == "mpeg4"
    assert metadata.container_format == "mov,mp4"
    assert metadata.warning_message is None
    assert len(calls) == 2
    assert calls[0][1]["shell"] is False
    assert (
        calls[0][1]["timeout"] == inspection_settings.video_inspection_timeout_seconds
    )
    assert calls[0][0][-1] == str(tiny_video)
    assert "-I" in calls[1][0]


@pytest.mark.parametrize(
    "invalid_response",
    [
        subprocess.CompletedProcess([], 1, ""),
        subprocess.CompletedProcess([], 0, "not json"),
        subprocess.CompletedProcess([], 0, "[]"),
        subprocess.CompletedProcess([], 0, '{"streams": []}'),
        probe_output(codec_type="audio"),
        probe_output(width=0),
        probe_output(width=1.5),
        probe_output(width=True),
        probe_output(width=50000),
        probe_output(height=-1),
        probe_output(duration="nan"),
        probe_output(duration="inf"),
        probe_output(duration="0"),
        probe_output(duration="90000"),
        probe_output(avg_frame_rate="500/1"),
        probe_output(avg_frame_rate="0/0", r_frame_rate="0/0"),
        probe_output(nb_frames="-1"),
    ],
)
def test_malformed_probe_or_invalid_metadata_never_falls_back(
    tmp_path, inspection_settings, invalid_response
):
    fake = tmp_path / "corrupt.mp4"
    fake.write_bytes(b"not a video")
    with patch(
        "app.services.video_inspection.subprocess.run", return_value=invalid_response
    ) as run:
        with pytest.raises(DomainError) as error:
            inspect_video(fake, inspection_settings)
    assert error.value.status_code == 422
    assert run.call_count == 1
    assert str(fake) not in error.value.detail


def test_fallback_rejects_corrupt_video_with_plausible_extension(
    tmp_path, inspection_settings
):
    path = tmp_path / "corrupt.mp4"
    path.write_bytes(b"This is an explicitly corrupt test video.")
    with pytest.raises(DomainError) as error:
        inspect_video(path, inspection_settings)
    assert error.value.status_code == 422


def test_probe_success_cannot_hide_decoder_failure(tmp_path, inspection_settings):
    path = tmp_path / "metadata-only.mp4"
    path.write_bytes(b"no real frames")
    original_run = subprocess.run
    calls = 0

    def run(args, **kwargs):
        nonlocal calls
        calls += 1
        return probe_output() if calls == 1 else original_run(args, **kwargs)

    with patch("app.services.video_inspection.subprocess.run", side_effect=run):
        with pytest.raises(DomainError) as error:
            inspect_video(path, inspection_settings)
    assert error.value.status_code == 422
    assert calls == 2


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_empty_file_rejected(tmp_path, inspection_settings, missing):
    path = tmp_path / "empty.mp4"
    if not missing:
        path.touch()
    with pytest.raises(DomainError) as error:
        inspect_video(path, inspection_settings)
    assert error.value.status_code == 422


@pytest.mark.parametrize("stage", ["ffprobe", "decode"])
def test_subprocess_timeouts_return_safe_errors(tmp_path, inspection_settings, stage):
    path = tmp_path / "timeout.mp4"
    path.write_bytes(b"test-only mock bytes")
    timeout = subprocess.TimeoutExpired(["private-server-path"], 1)
    responses = [timeout] if stage == "ffprobe" else [probe_output(), timeout]
    with patch("app.services.video_inspection.subprocess.run", side_effect=responses):
        with pytest.raises(DomainError) as error:
            inspect_video(path, inspection_settings)
    assert error.value.status_code == 422
    assert "timed out" in error.value.detail
    assert "private-server-path" not in error.value.detail


def test_missing_decoder_is_a_capability_error(tmp_path, inspection_settings):
    path = tmp_path / "mock.mp4"
    path.write_bytes(b"test-only mock bytes")
    with patch(
        "app.services.video_inspection.subprocess.run",
        side_effect=[
            probe_output(),
            subprocess.CompletedProcess([], 0, '{"error": "unavailable"}'),
        ],
    ):
        with pytest.raises(DomainError) as error:
            inspect_video(path, inspection_settings)
    assert error.value.status_code == 503


def test_probe_operating_system_failure_is_not_a_fallback(
    tmp_path, inspection_settings
):
    path = tmp_path / "mock.mp4"
    path.write_bytes(b"test-only mock bytes")
    with patch(
        "app.services.video_inspection.subprocess.run", side_effect=PermissionError()
    ) as run:
        with pytest.raises(DomainError) as error:
            inspect_video(path, inspection_settings)
    assert error.value.status_code == 503
    assert run.call_count == 1


def test_fallback_rejects_real_avi_renamed_as_mp4(tmp_path, inspection_settings):
    avi_path = tmp_path / "synthetic.avi"
    writer = cv2.VideoWriter(
        str(avi_path), cv2.VideoWriter_fourcc(*"MJPG"), 12, (48, 32)
    )
    assert writer.isOpened()
    try:
        writer.write(np.zeros((32, 48, 3), dtype=np.uint8))
    finally:
        writer.release()
    renamed = tmp_path / "renamed.mp4"
    avi_path.rename(renamed)
    with pytest.raises(DomainError) as error:
        inspect_video(renamed, inspection_settings)
    assert error.value.status_code == 422


def test_fallback_decoder_does_not_follow_playlist_files(tmp_path, inspection_settings):
    playlist = tmp_path / "playlist.mp4"
    playlist.write_text("#EXTM3U\n#EXTINF:1\nhttp://example.invalid/video.ts\n")
    with patch("app.services.video_inspection._decode") as decoder:
        with pytest.raises(DomainError):
            inspect_video(playlist, inspection_settings)
    decoder.assert_not_called()


@pytest.mark.parametrize("frame_count", [None, 0, -1, "NaN"])
def test_fallback_does_not_invent_duration(tmp_path, inspection_settings, frame_count):
    path = tmp_path / "mock.mp4"
    path.write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x00\x00")
    decoded = {"width": 48, "height": 32, "fps": 12, "frame_count": frame_count}
    with patch("app.services.video_inspection._run_probe", return_value=None):
        with patch("app.services.video_inspection._decode", return_value=decoded):
            with pytest.raises(DomainError) as error:
                inspect_video(path, inspection_settings)
    assert error.value.status_code == 422


def test_probe_stream_fps_and_duration_fallbacks(tiny_video, inspection_settings):
    result = probe_output(avg_frame_rate="0/0", duration="N/A", nb_frames="N/A")
    payload = json.loads(result.stdout)
    payload["format"]["duration"] = "0.5"
    result.stdout = json.dumps(payload)
    original_run = subprocess.run
    calls = 0

    def run(args, **kwargs):
        nonlocal calls
        calls += 1
        return result if calls == 1 else original_run(args, **kwargs)

    with patch("app.services.video_inspection.subprocess.run", side_effect=run):
        metadata = inspect_video(tiny_video, inspection_settings)
    assert metadata.fps == 12
    assert metadata.duration_seconds == 0.5
    assert metadata.frame_count is None


def test_probe_non_utf8_output_is_rejected_safely(tmp_path, inspection_settings):
    path = tmp_path / "mock.mp4"
    path.write_bytes(b"test-only mock bytes")
    malformed = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
    with patch("app.services.video_inspection.subprocess.run", side_effect=malformed):
        with pytest.raises(DomainError) as error:
            inspect_video(path, inspection_settings)
    assert error.value.status_code == 422
