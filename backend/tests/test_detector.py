"""Synthetic boxes/frames only; normal tests never load weights or run YOLO."""

import csv
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.cv import detector, pipeline, video
from app.cv.detector import Detection, DetectionError, YoloPlayerDetector, select_device
from app.cv.roi import build_pitch_roi
from app.cv.video import VideoFrame, VideoFrames
from app.services.detection_artifacts import COLUMNS, DetectionArtifact


def model_results(rows):
    data = np.asarray(rows, dtype=float).reshape(-1, 6)
    boxes = Mock(xyxy=data[:, :4], conf=data[:, 4])
    boxes.cls = data[:, 5]
    boxes.cpu.return_value = boxes
    boxes.numpy.return_value = boxes
    return [SimpleNamespace(boxes=boxes)]


@pytest.fixture
def model(monkeypatch):
    fake = Mock(task="detect", names={0: "person", 1: "bicycle", 32: "sports ball"})
    fake.predict.return_value = model_results([])
    monkeypatch.setattr(detector, "_load_model", lambda _settings: fake)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )
    return fake


def test_yolo_keeps_people_down_to_the_tracking_floor_in_original_pixels(
    settings, model
):
    settings.yolo_confidence = settings.track_high_thresh = 0.5
    settings.track_low_thresh = 0.3
    settings.yolo_image_size = 320
    model.predict.return_value = model_results(
        [
            [10, 20, 80, 90, 0.8, 0],
            [10, 20, 30, 40, 0.49, 0],  # Unreported ByteTrack candidate.
            [10, 20, 30, 40, 0.29, 0],  # Below TRACK_LOW_THRESH: never stored.
            [1, 2, 3, 4, 0.99, 1],
            [1, 2, 3, 4, 0.99, 32],
            [-1, -2, 110, 120, 0.5, 0],
        ]
    )
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    subject = YoloPlayerDetector(settings)
    assert subject.detect(image) == [
        Detection((10, 20, 80, 90), 0.8, 0, "person"),
        Detection((10, 20, 30, 40), 0.49, 0, "person"),
        Detection((0, 0, 100, 100), 0.5, 0, "person"),
    ]
    kwargs = model.predict.call_args.kwargs
    assert kwargs["source"] is image
    assert {
        key: kwargs[key] for key in ("conf", "classes", "imgsz", "device", "save")
    } == {
        "conf": 0.3,
        "classes": [0],
        "imgsz": 320,
        "device": "cpu",
        "save": False,
    }


def test_empty_detection_is_empty_data(settings, model):
    assert YoloPlayerDetector(settings).detect(np.zeros((48, 64, 3), np.uint8)) == []


@pytest.mark.parametrize(
    "row",
    [
        [0, 0, 20, 20, float("nan"), 0],
        [0, 0, 20, 20, 1.1, 0],
        [0, 0, 20, 20, 0.8, 0.5],
        [10, 0, 5, 20, 0.8, 0],
        [0, 0, float("inf"), 20, 0.8, 0],
    ],
)
def test_invalid_model_output_fails_safely(settings, model, row):
    model.predict.return_value = model_results([row])
    with pytest.raises(DetectionError, match="YOLO detection failed"):
        YoloPlayerDetector(settings).detect(np.zeros((48, 64, 3), np.uint8))


@pytest.mark.parametrize(
    "requested,available,expected",
    [
        ("auto", False, "cpu"),
        ("auto", True, "cuda:0"),
        ("cpu", True, "cpu"),
        ("cuda", True, "cuda:0"),
        ("cuda:1", True, "cuda:1"),
    ],
)
def test_device_selection(requested, available, expected):
    assert select_device(requested, available) == expected


def test_explicit_cuda_requires_available_device():
    with pytest.raises(DetectionError, match="CUDA is unavailable"):
        select_device("cuda:0", False)


def test_model_load_and_wrong_model_fail_with_safe_messages(
    settings, model, monkeypatch
):
    model.names = {0: "car"}
    with pytest.raises(DetectionError, match="person class"):
        YoloPlayerDetector(settings)
    monkeypatch.setattr(
        detector, "_load_model", Mock(side_effect=RuntimeError("private/model/path"))
    )
    with pytest.raises(DetectionError, match="could not be loaded") as caught:
        YoloPlayerDetector(settings)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "values",
    [
        {"detection_frame_stride": 0},
        {"yolo_image_size": 33},
        {"yolo_confidence": float("nan")},
        {"device": "bad"},
        {"yolo_model": "untrained.yaml"},
        {"detection_job_timeout_seconds": 0},
    ],
)
def test_detection_settings_validate(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def corners():
    return (
        [{"x": x, "y": y} for x, y in [(10, 10), (110, 10), (110, 90), (10, 90)]],
        [{"x": x, "y": y} for x, y in [(0, 0), (60, 0), (60, 36), (0, 36)]],
    )


def test_roi_uses_bottom_centre_and_requires_complete_explicit_pitch_corners():
    images, pitch = corners()
    roi = build_pitch_roi(images, pitch, 60, 36, 120, 100)
    assert roi is not None
    # Box centre is outside but its bottom centre is on the pitch.
    assert roi.contains(Detection((20, -50, 50, 30), 0.9, 0, "person"))
    assert not roi.contains(Detection((20, 20, 50, 99), 0.9, 0, "person"))
    assert roi.contains(Detection((20, 20, 50, 91), 0.9, 0, "person"))
    pitch[0] = {"x": 20, "y": 10}
    assert build_pitch_roi(images, pitch, 60, 36, 120, 100) is None


@pytest.mark.parametrize(
    "fault", ["crossed", "collinear", "out_of_bounds", "duplicate", "nan"]
)
def test_unsafe_roi_geometry_is_skipped(fault):
    images, pitch = corners()
    if fault == "crossed":
        images[1], images[2] = images[2], images[1]
    elif fault == "collinear":
        images = [{"x": index * 10, "y": 20} for index in range(4)]
    elif fault == "out_of_bounds":
        images[0]["x"] = -1
    elif fault == "duplicate":
        images.append(images[0])
        pitch.append(pitch[0])
    else:
        images[0]["x"] = float("nan")
    assert build_pitch_roi(images, pitch, 60, 36, 120, 100) is None


class SyntheticCapture:
    def __init__(self, timestamps, reported_count=None):
        self.timestamps = timestamps
        self.index = 0
        self.reported_count = (
            len(timestamps) if reported_count is None else reported_count
        )
        self.released = False

    def open(self, *_args):
        return True

    def get(self, prop):
        return {
            cv2.CAP_PROP_FPS: 10,
            cv2.CAP_PROP_FRAME_COUNT: self.reported_count,
            cv2.CAP_PROP_FRAME_WIDTH: 64,
            cv2.CAP_PROP_FRAME_HEIGHT: 48,
            cv2.CAP_PROP_POS_MSEC: self.timestamps[max(0, self.index - 1)],
        }[prop]

    def read(self):
        if self.index == len(self.timestamps):
            return False, None
        self.index += 1
        return True, np.full((48, 64, 3), self.index, dtype=np.uint8)

    def release(self):
        self.released = True


def test_incremental_sampling_preserves_decoded_timestamps_and_counts_empty_frames(
    monkeypatch, tmp_path
):
    capture = SyntheticCapture([0, 80, 230, 400])
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda: capture)
    mock_detector = Mock(detect=Mock(return_value=[]))
    rows = []
    progress = []
    run = pipeline.detect_video(
        tmp_path / "fixture.mp4",
        mock_detector,
        stride=2,
        image_width=64,
        image_height=48,
        roi=None,
        confidence_threshold=0.25,
        write_frame=lambda frame, detected: rows.append(
            (frame.number, frame.timestamp_seconds, detected)
        ),
        progress=lambda decoded, total: progress.append((decoded, total)),
    )
    assert rows == [(0, 0.0, []), (2, 0.23, [])]
    assert run == pipeline.DetectionRun(2, 4, 0, 0)
    assert mock_detector.detect.call_count == 2 and capture.released
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_counts_report_only_confident_boxes_but_candidates_are_stored(
    monkeypatch, tmp_path
):
    capture = SyntheticCapture([0, 100])
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda: capture)
    candidates = [
        Detection((1, 1, 9, 9), 0.9, 0, "person"),
        Detection((20, 1, 29, 9), 0.25, 0, "person"),  # Exactly YOLO_CONFIDENCE.
        Detection((40, 1, 49, 9), 0.15, 0, "person"),  # ByteTrack-only candidate.
    ]
    written = []
    run = pipeline.detect_video(
        tmp_path / "fixture.mp4",
        Mock(detect=Mock(return_value=candidates)),
        stride=1,
        image_width=64,
        image_height=48,
        roi=None,
        confidence_threshold=0.25,
        write_frame=lambda frame, detected: written.append(detected),
        progress=lambda *_: None,
    )
    assert written == [candidates, candidates]
    assert run == pipeline.DetectionRun(2, 2, 4, 0, low_confidence_detections=2)


def test_timestamp_fallback_is_explicit_and_early_eof_is_a_failure(
    monkeypatch, tmp_path
):
    capture = SyntheticCapture([0, 0, float("nan")], reported_count=4)
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda: capture)
    read = []
    with pytest.raises(DetectionError, match="ended before"):
        with VideoFrames(tmp_path / "fixture.mp4") as frames:
            read.extend(frames)
    assert [frame.timestamp_seconds for frame in read] == [0.0, 0.1, 0.2]
    assert [frame.timestamp_estimated for frame in read] == [False, True, True]
    assert capture.released


def test_csv_records_exact_pixels_and_metadata_and_empty_results_have_headers(settings):
    frame = VideoFrame(7, 0.25, np.zeros((48, 64, 3), np.uint8), False)
    with DetectionArtifact(settings, 1, 2, 3, 0) as artifact:
        artifact.write_frame(frame, [Detection((2.5, 4, 30, 40), 0.75, 0, "person")])
        assert not artifact.path.exists()
        artifact.publish()
        artifact.keep()
    with artifact.path.open(newline="", encoding="utf-8") as stream:
        assert list(csv.DictReader(stream)) == [
            dict(
                zip(
                    COLUMNS,
                    [
                        "7",
                        "0.25",
                        "2.5",
                        "4",
                        "30",
                        "40",
                        "0.75",
                        "0",
                        "person",
                        "64",
                        "48",
                    ],
                    strict=True,
                )
            )
        ]
    with DetectionArtifact(settings, 1, 2, 4, 0) as empty:
        empty.write_frame(frame, [])
        empty.publish()
        empty.keep()
    assert empty.path.read_text().strip() == ",".join(COLUMNS)


def test_partial_or_uncommitted_csv_is_removed(settings):
    with pytest.raises(RuntimeError):
        with DetectionArtifact(settings, 1, 2, 3, 0) as artifact:
            artifact.publish()
            raise RuntimeError("synthetic DB commit failure")
    assert not artifact.path.exists() and not artifact.temporary.exists()
