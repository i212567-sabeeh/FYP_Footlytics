"""Real ByteTrack on explicit synthetic boxes: no model, downloads or inference."""

import inspect
import re
from importlib import metadata

import pytest
from packaging.specifiers import SpecifierSet
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.cv.detector import Detection
from app.cv.tracker import BaseTracker, ByteTrackTracker, TrackingError
from app.cv.tracking_rows import within_video


def person(x=10, confidence=0.9):
    return Detection((x, 10, x + 20, 70), confidence, 0, "person")


def tracker(settings, match_id=1):
    return ByteTrackTracker(
        settings, match_id=match_id, image_width=320, image_height=200
    )


def test_consecutive_frames_keep_two_distinct_ids(settings):
    instance = tracker(settings)
    assert isinstance(instance, BaseTracker)
    first = instance.update([person(), person(100)])
    for offset in (1, 2, 3):
        tracks = instance.update([person(10 + offset), person(100 + offset)])
        assert [item.track_id for item in tracks] == [item.track_id for item in first]
        assert len({item.track_id for item in tracks}) == 2
        assert all(0 <= item.bbox[0] < item.bbox[2] <= 320 for item in tracks)
        assert all(item.confidence == pytest.approx(0.9) for item in tracks)


def test_empty_frame_and_short_gap_keep_id_without_invented_rows(settings):
    instance = tracker(settings)
    first = instance.update([person()])[0]
    assert instance.update([]) == []
    assert instance.update([]) == []
    recovered = instance.update([person(11)])[0]
    assert recovered.track_id == first.track_id


def test_low_confidence_second_association_and_new_track_threshold(settings):
    settings.track_high_thresh = 0.6
    instance = tracker(settings)
    first = instance.update([person()])[0]
    tracks = instance.update([person(11, 0.2), person(100, 0.3)])
    assert len(tracks) == 1 and tracks[0].track_id == first.track_id
    assert tracks[0].confidence == pytest.approx(0.2)
    assert instance.update([person(12, 0.05)]) == []


def test_buffer_expiry_does_not_resurrect_old_id(settings):
    settings.track_buffer = 1
    instance = tracker(settings)
    first = instance.update([person()])[0]
    for _ in range(4):
        assert instance.update([]) == []
    instance.update([person()])
    assert instance.update([person()])[0].track_id != first.track_id


@pytest.mark.parametrize(
    "buffer,stride,updates",
    [(30, 1, 30), (30, 5, 6), (30, 4, 7), (30, 31, 1), (1, 1, 1)],
)
def test_track_buffer_counts_source_frames_at_any_stride(
    settings, buffer, stride, updates
):
    settings.track_buffer = buffer
    instance = ByteTrackTracker(
        settings, match_id=1, image_width=320, image_height=200, frame_stride=stride
    )
    assert instance.track_buffer_updates == updates


def test_sampled_lost_track_memory_is_converted_from_source_frames(settings):
    settings.track_buffer = 4
    instance = ByteTrackTracker(
        settings, match_id=1, image_width=320, image_height=200, frame_stride=2
    )
    first = instance.update([person()])[0]
    # Upstream ByteTrack recovers a track after buffer + 1 missed updates, as at
    # stride 1; here that is 2 + 1 sampled updates.
    for _ in range(3):
        assert instance.update([]) == []
    assert instance.update([person()])[0].track_id == first.track_id
    # Unconverted, the 4-update buffer kept this ID through 8 missed source frames.
    for _ in range(4):
        assert instance.update([]) == []
    assert instance.update([person()]) == []  # New tracks need confirmation.
    assert instance.update([person()])[0].track_id != first.track_id


def test_frame_stride_must_be_positive(settings):
    with pytest.raises(TrackingError, match="frame stride"):
        ByteTrackTracker(
            settings, match_id=1, image_width=320, image_height=200, frame_stride=0
        )


def test_interleaved_matches_have_independent_counters(settings):
    first = tracker(settings, 11)
    assert first.update([person()])[0].track_id == 1
    second = tracker(settings, 22)
    assert second.update([person()])[0].track_id == 1
    first.update([person(), person(100)])
    second.update([person(), person(100)])
    assert {t.track_id for t in first.update([person(), person(100)])} == {1, 2}
    assert {t.track_id for t in second.update([person(), person(100)])} == {1, 2}


@pytest.mark.parametrize(
    "box",
    [
        (10, 10, 10, 40),
        (20, 10, 10, 40),
        (0, 0, 10, 0),
        (-1, 0, 10, 10),
        (0, 0, 321, 10),
        (0, 0, 10, 201),
        (float("nan"), 0, 10, 10),
        (0, 0, float("inf"), 10),
    ],
)
def test_invalid_boxes_are_rejected(settings, box):
    with pytest.raises(TrackingError, match="invalid person box"):
        tracker(settings).update([Detection(box, 0.9, 0, "person")])


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence_is_rejected(settings, confidence):
    with pytest.raises(TrackingError):
        tracker(settings).update([person(confidence=confidence)])


def test_nonperson_detections_are_rejected(settings):
    with pytest.raises(TrackingError):
        tracker(settings).update([Detection((1, 1, 10, 10), 0.9, 1, "bicycle")])


@pytest.mark.parametrize(
    "values",
    [
        {"track_low_thresh": 0.6, "track_high_thresh": 0.5},
        {"track_low_thresh": 0.25},
        {"track_high_thresh": 0},
        {"track_match_thresh": 1.1},
        {"track_buffer": 0},
        {"track_high_thresh": float("nan")},
        {"track_low_thresh": 0},  # Would make YOLO store every candidate.
        {"track_high_thresh": 0.2},  # Tracks could start from unreported boxes.
        {"yolo_confidence": 0.3},
    ],
)
def test_invalid_tracker_settings_fail_early(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_detection_candidates_cover_the_bytetrack_low_band():
    assert Settings(_env_file=None).detection_candidate_confidence == 0.1
    lenient = Settings(_env_file=None, yolo_confidence=0.05)
    assert lenient.detection_candidate_confidence == 0.05


@pytest.mark.parametrize(
    "seconds,duration,expected",
    [
        (0, 0.4, True),
        (0.399, 0.4, True),
        (0.4, 0.4, False),  # A frame cannot start at the reported end.
        (0.5, 0.4, False),
        (-0.001, 0.4, False),
        (float("nan"), 0.4, False),
        (float("inf"), 0.4, False),
        (0.1, 0, False),
        (0.1, float("inf"), False),
    ],
)
def test_track_timestamps_share_one_duration_rule(seconds, duration, expected):
    assert within_video(seconds, duration) is expected


def test_installed_ultralytics_is_a_verified_bytetrack_release():
    """tracker.py subclasses private ByteTrack API verified at both pinned ends."""
    backend = PROJECT_ROOT / "backend"
    name = "ultralytics-opencv-headless"
    requirement = next(
        line
        for line in (backend / "requirements.txt").read_text().splitlines()
        if line.startswith(name)
    )
    allowed = SpecifierSet(requirement.removeprefix(name))
    # Exactly the verified releases' range; widen only after re-verification.
    assert "8.4.166" in allowed and "8.4.170" in allowed
    assert "8.4.165" not in allowed and "8.4.171" not in allowed
    assert metadata.version(name) in allowed
    for lock in ("requirements-dev.lock", "requirements-wsl-cpu.lock"):
        pinned = re.search(rf"^{name}==(\S+)", (backend / lock).read_text(), re.M)
        assert pinned is not None and pinned[1] in allowed
    from ultralytics.trackers.byte_tracker import BYTETracker

    assert list(inspect.signature(BYTETracker.__init__).parameters) == ["self", "args"]
    assert list(inspect.signature(BYTETracker.init_track).parameters) == [
        "self",
        "results",
        "img",
    ]
