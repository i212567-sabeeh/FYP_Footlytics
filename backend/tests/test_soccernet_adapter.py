"""Small synthetic schema fixtures test conversion, never real CV accuracy."""

import os
from copy import deepcopy

import cv2
import numpy as np
import pytest

from app.evaluation.adapters.soccernet_gsr import (
    convert_annotations,
    convert_soccernet_pitch_to_footlytics,
    pixel_box,
    source_frame_number,
    team_mapping_from_reference_colors,
)
from app.evaluation.schemas import InputError
from app.evaluation.soccernet import lossless_video

MAPPING = {"left": "team_b", "right": "team_a"}


@pytest.fixture(autouse=True)
def restore_decoder_environment(monkeypatch):
    for key in ("OPENCV_FFMPEG_CAPTURE_OPTIONS", "OPENCV_FFMPEG_THREADS"):
        monkeypatch.setenv(key, os.environ.get(key, ""))


@pytest.fixture
def gsr_data():
    images = [
        dict(
            image_id=f"opaque-{9 - n}",
            file_name=f"{n + 1:06d}.jpg",
            width=100,
            height=80,
            is_labeled=True,
            has_labeled_person=True,
            ignore_regions_x=[],
            ignore_regions_y=[],
        )
        for n in range(3)
    ]
    annotations = []
    for im in images:
        for identity, role, category, team in (
            (1, "player", 1, "left"),
            (2, "goalkeeper", 2, "right"),
            (3, "referee", 3, None),
            (4, "ball", 4, None),
            (5, "other", 7, None),
        ):
            annotations.append(
                dict(
                    image_id=im["image_id"],
                    track_id=identity,
                    supercategory="object",
                    category_id=category,
                    attributes=dict(role=role, team=team),
                    bbox_image=dict(x=10, y=20, w=20, h=30, x_center=20, y_center=35),
                    bbox_pitch=dict(x_bottom_middle=0, y_bottom_middle=0),
                )
            )
        annotations.append(dict(image_id=im["image_id"], category_id=5, lines={}))
    return dict(
        info=dict(version="1.3", name="SNGS-021", frame_rate=25, seq_length=3),
        images=images,
        annotations=annotations,
    )


def test_real_schema_conversion_roles_ids_and_reviewed_frames(gsr_data):
    converted = convert_annotations(gsr_data, frame_count=3, team_mapping=MAPPING)
    assert [f.number for f in converted.frames] == [0, 1, 2]
    assert [f.timestamp for f in converted.frames] == [0, 0.04, 0.08]
    assert len(converted.observations) == 12
    assert converted.observations[0].box == (10, 20, 30, 50)
    assert converted.observations[0].pitch == (52.5, 34)
    assert converted.observations[0].team == "team_b"
    assert converted.observations[1].team == "team_a"
    assert converted.observations[2].ignored
    assert converted.observations[3].ignored
    assert {r.track_id for r in converted.observations if not r.ignored} == {"1", "2"}
    assert converted.diagnostics["roles"]["ball"] == 3


def test_opaque_image_ids_are_joined_by_filename_not_numerical_suffix(gsr_data):
    gsr_data["images"].reverse()
    converted = convert_annotations(gsr_data, frame_count=2, team_mapping=MAPPING)
    assert len(converted.frames) == 2
    assert converted.source_images[0]["image_id"] == "opaque-9"
    assert {r.frame for r in converted.observations} == {0, 1}


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("000001.jpg", 0), ("000375.jpg", 374), ("000750.jpg", 749)],
)
def test_early_middle_late_alignment(filename, expected):
    assert source_frame_number(filename) == expected


@pytest.mark.parametrize(
    "filename", ["000000.jpg", "1.jpg", "../000001.jpg", "000001.png", "000001.JPG", 1]
)
def test_invalid_frame_names(filename):
    with pytest.raises(InputError):
        source_frame_number(filename)


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((0, 0), (52.5, 34)),
        ((-52.5, -34), (0, 0)),
        ((52.5, 34), (105, 68)),
        ((52.5, -34), (105, 0)),
        ((-52.5, 34), (0, 68)),
        ((0, -34), (52.5, 0)),
        ((0, 34), (52.5, 68)),
        ((-60, 0), (-7.5, 34)),
    ],
)
def test_coordinate_axes_and_known_landmarks(point, expected):
    assert (
        convert_soccernet_pitch_to_footlytics(
            *point,
            source_length_metres=105,
            source_width_metres=68,
            target_length_metres=105,
            target_width_metres=68,
        )
        == expected
    )


def test_coordinate_rescaling_is_explicit():
    assert convert_soccernet_pitch_to_footlytics(
        52.5,
        -34,
        source_length_metres=105,
        source_width_metres=68,
        target_length_metres=40,
        target_width_metres=20,
    ) == (40, 0)


@pytest.mark.parametrize(
    "change",
    [
        {"x": float("nan")},
        {"y": float("inf")},
        {"source_length_metres": 0},
        {"target_width_metres": -1},
        {"x": True},
    ],
)
def test_bad_coordinate_values(change):
    kwargs = (
        dict(
            x=0,
            y=0,
            source_length_metres=105,
            source_width_metres=68,
            target_length_metres=105,
            target_width_metres=68,
        )
        | change
    )
    with pytest.raises(InputError):
        convert_soccernet_pitch_to_footlytics(**kwargs)


def test_independent_team_order_is_not_left_equals_a():
    assert (
        team_mapping_from_reference_colors({"left": (90, 0, 0), "right": (30, 4, -25)})
        == MAPPING
    )
    assert team_mapping_from_reference_colors(
        {"left": (30, 4, -25), "right": (90, 0, 0)}
    ) == {"left": "team_a", "right": "team_b"}


@pytest.mark.parametrize(
    "colors",
    [
        {"left": (10, 0, 0)},
        {"left": (10, 0, 0), "right": (10, 0, 0)},
        {"left": (float("nan"), 0, 0), "right": (20, 0, 0)},
        {"left": (110, 0, 0), "right": (20, 0, 0)},
    ],
)
def test_unestablished_team_mapping_is_rejected(colors):
    with pytest.raises(InputError):
        team_mapping_from_reference_colors(colors)


@pytest.mark.parametrize(
    "change",
    [
        {"x": -1},
        {"w": 0},
        {"x": 95},
        {"h": float("nan")},
        {"normalized": True},
        {"x_center": 99},
    ],
)
def test_invalid_boxes_are_not_silently_repaired(change):
    with pytest.raises(InputError):
        pixel_box(dict(x=10, y=20, w=20, h=30) | change, 100, 80)


def test_small_pixel_boxes_are_not_assumed_normalized():
    assert pixel_box(dict(x=0.1, y=0.2, w=0.3, h=0.4), 100, 80) == pytest.approx(
        (0.1, 0.2, 0.4, 0.6)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["info"].update(version="1.2"),
        lambda d: d["info"].update(frame_rate=0),
        lambda d: d["images"].pop(),
        lambda d: d["images"][1].update(file_name="000001.jpg"),
        lambda d: d["images"][1].update(image_id="opaque-9"),
        lambda d: d["images"][0].update(has_labeled_person=False),
        lambda d: d["images"][0].update(ignore_regions_x=[[1, 2, 3]]),
        lambda d: d["annotations"][0].update(image_id="missing"),
        lambda d: d["annotations"][0].update(track_id=True),
        lambda d: d["annotations"][0].update(category_id=99),
        lambda d: d["annotations"][0]["attributes"].update(role="goalkeeper"),
        lambda d: d["annotations"][0]["attributes"].update(team="home"),
        lambda d: d["annotations"][0]["bbox_image"].pop("w"),
        lambda d: d["annotations"].append(deepcopy(d["annotations"][0])),
        lambda d: d["annotations"][6]["attributes"].update(team="right"),
    ],
)
def test_bad_schema_and_inconsistent_gt_fail(gsr_data, mutation):
    mutation(gsr_data)
    with pytest.raises(InputError):
        convert_annotations(gsr_data, frame_count=3, team_mapping=MAPPING)


def test_missing_pitch_and_unknown_team_stay_missing(gsr_data):
    for row in gsr_data["annotations"]:
        if row.get("track_id") == 1:
            row["bbox_pitch"] = None
            row["attributes"]["team"] = None
    converted = convert_annotations(gsr_data, frame_count=3, team_mapping=MAPPING)
    assert converted.observations[0].pitch is None
    assert converted.observations[0].team == "unknown"


def test_empty_reviewed_frame_is_retained(gsr_data):
    gsr_data["annotations"] = [
        a for a in gsr_data["annotations"] if a["image_id"] != "opaque-8"
    ]
    converted = convert_annotations(gsr_data, frame_count=3, team_mapping=MAPPING)
    assert len(converted.frames) == 3
    assert not any(r.frame == 1 for r in converted.observations)


def test_lossless_movie_preserves_frames_for_production_decoder(gsr_data, tmp_path):
    from app.cv.video import VideoFrames

    converted = convert_annotations(gsr_data, frame_count=3, team_mapping=MAPPING)
    (tmp_path / "img1").mkdir()
    for number in range(3):
        image = np.full((80, 100, 3), 30 + number * 60, dtype=np.uint8)
        assert cv2.imwrite(str(tmp_path / "img1" / f"{number + 1:06d}.jpg"), image)
    target = tmp_path / "subset.mov"
    aligned = lossless_video(tmp_path, converted, target)
    assert all(item["pixels_identical"] for item in aligned)
    with VideoFrames(target) as frames:
        decoded = list(frames)
    assert [f.number for f in decoded] == [0, 1, 2]
    assert [f.timestamp_seconds for f in decoded] == pytest.approx([0, 0.04, 0.08])


def test_production_pipeline_orchestration_with_small_stub_detections(
    gsr_data, tmp_path
):
    """Real ByteTrack/classifier plumbing; stub boxes are synthetic test data."""
    import csv
    from types import SimpleNamespace

    from app.core.config import Settings
    from app.cv.detector import BaseDetector, Detection
    from app.evaluation.inputs import sha256
    from app.evaluation.predict import predict_clip
    from app.evaluation.schemas import FileRef

    converted = convert_annotations(gsr_data, frame_count=3, team_mapping=MAPPING)
    (tmp_path / "img1").mkdir()
    for number in range(3):
        image = np.full((80, 100, 3), 50, dtype=np.uint8)
        assert cv2.imwrite(str(tmp_path / "img1" / f"{number + 1:06d}.jpg"), image)
    video = tmp_path / "pipeline.mov"
    lossless_video(tmp_path, converted, video)
    output = tmp_path / "artifacts"
    output.mkdir()

    class StubDetector(BaseDetector):
        model_name = "synthetic-fixture"
        device = "cpu"

        def detect(self, frame):
            return [
                Detection((10, 20, 30, 50), 0.9, 0, "person"),
                Detection((60, 20, 80, 50), 0.8, 0, "person"),
            ]

    clip = SimpleNamespace(
        clip_id="SNGS-021",
        frame_count=3,
        width=100,
        height=80,
        duration_seconds=0.12,
        video=FileRef(path="pipeline.mov", sha256=sha256(video)),
    )
    prediction, diagnostic = predict_clip(
        clip,
        video,
        output,
        Settings(_env_file=None, environment="test"),
        StubDetector(),
        {"cpu": "test CPU"},
        "a" * 64,
    )
    assert diagnostic["detection"]["processed_frames"] == 3
    assert diagnostic["tracking"]["unique_tracks"] == 2
    assert prediction.processed_frames == [0, 1, 2]
    assert {r.stage for r in prediction.runtime} == {
        "detection",
        "tracking",
        "team_classification",
    }
    with (output / "tracks.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert {r["track_id"] for r in rows if r["frame_number"] == "0"} == {
        r["track_id"] for r in rows if r["frame_number"] == "2"
    }


def test_soccernet_omits_unavailable_coordinate_csv_without_inventing_scores(tmp_path):
    from app.evaluation.reporting import evaluate, publish
    from app.evaluation.run import empty_dataset
    from app.evaluation.schemas import EvaluationConfig

    summary = evaluate(
        empty_dataset("Synthetic unit test of unavailable publication"),
        [],
        None,
        EvaluationConfig(),
        {},
    )
    output = publish(summary, tmp_path, {}, write_coordinate_metrics=False)
    assert not (output / "coordinate_metrics.csv").exists()
    assert (output / "evaluation_summary.json").exists()
    assert summary["coordinates"]["player_coordinates"]["rmse"] is None


def test_distinct_game_selection_is_sorted_and_metadata_only():
    from app.evaluation.adapters.soccernet_gsr import select_distinct_source_games

    records = [
        {"clip_id": "SNGS-078", "game_id": "5"},
        {"clip_id": "SNGS-022", "game_id": "2"},
        {"clip_id": "SNGS-039", "game_id": "3"},
        {"clip_id": "SNGS-021", "game_id": "2"},
        {"clip_id": "SNGS-040", "game_id": "3"},
    ]
    assert select_distinct_source_games(records) == ["SNGS-021", "SNGS-039", "SNGS-078"]


def test_distinct_game_selection_does_not_invent_diversity():
    from app.evaluation.adapters.soccernet_gsr import select_distinct_source_games

    with pytest.raises(InputError, match="Fewer"):
        select_distinct_source_games(
            [
                {"clip_id": "SNGS-021", "game_id": "2"},
                {"clip_id": "SNGS-022", "game_id": "2"},
            ]
        )


@pytest.mark.parametrize(
    "record",
    [
        {"clip_id": "SNGS-021"},
        {"clip_id": "SNGS-021", "game_id": None},
        {"clip_id": "SNGS-021", "game_id": True},
        {"clip_id": "invalid", "game_id": "2"},
    ],
)
def test_distinct_game_selection_rejects_missing_or_invalid_metadata(record):
    from app.evaluation.adapters.soccernet_gsr import select_distinct_source_games

    with pytest.raises(InputError):
        select_distinct_source_games([record])
