"""Portable PDF layout, safe plain-text rendering and strict validation."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from report_fixtures import player, team
from reportlab.graphics.shapes import Rect

from app.reports.builder import build_report, duration, heatmap_drawing
from app.reports.data import ReportData
from app.schemas.player_analytics import HeatmapCell, TrackHeatmapRead
from app.services.domain_common import DomainError
from app.services.report_artifacts import ReportArtifact, validate_pdf
from app.services.report_service import csv_cell


@pytest.fixture
def report_data():
    return ReportData(
        metadata=dict(
            match_id=42,
            title='United <img src="/private/secret"> & Rovers',
            club="Local Club",
            team_a="United",
            team_b="Rovers",
            match_date="2026-10-04",
            match_format="5v5",
            venue=None,
            pitch_length_metres=30,
            pitch_width_metres=20,
        ),
        generated_at=datetime(2026, 10, 4, 12, tzinfo=UTC),
        assignments={1: "team_a", 2: "team_b"},
        players=[player(), player(2, True)],
        teams=[team(), team("team_b", True)],
        heatmaps=[],
        unavailable={},
        source_jobs={},
        sprint_threshold_mps=7,
        sprint_min_duration_seconds=0.1,
        heatmap_limit=4,
    )


def test_pdf_content_nulls_units_safe_markup_and_determinism(tmp_path, report_data):
    one, two = tmp_path / "one.pdf", tmp_path / "two.pdf"
    build_report(report_data, one)
    build_report(report_data, two)
    assert one.read_bytes() == two.read_bytes()
    pages, size = validate_pdf(one)
    assert pages >= 4 and size > 1000
    reader = PdfReader(one)
    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in (
        "FOOTLYTICS",
        "Match 42",
        "United",
        "Rovers",
        "Unavailable",
        "36.0",
        "0:00.1",
        "Track 2",
        "Team A",
        "Team B",
        "Average width (Y range)",
        "Average depth (X range)",
        "3.0 m",
        "4.0 m",
        "2.3 m",
        "Methodology and limitations",
    ):
        assert expected in text
    assert (
        'img src="/private/secret"' in text
    )  # Literal text, never an external image/file read.
    assert "nan" not in text.lower().split() and "None" not in text
    assert all(
        f"Page {i}" in page.extract_text() for i, page in enumerate(reader.pages, 1)
    )


def test_unmeasured_movement_is_a_dash_and_speed_window_is_stated(
    tmp_path, report_data
):
    path = tmp_path / "report.pdf"
    build_report(replace(report_data, speed_window_seconds=0.2), path)
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    # Track 2 has no measured movement window: no zero distance or sprint count.
    # Extracted table cells are one per line, in column order.
    lines = text.splitlines()
    start = lines.index("Track 2")
    assert lines[start + 1 : start + 9] == [
        "Team B",
        "—",
        "0:00.0",
        "—",
        "—",
        "—",
        "—",
        "—",
    ]
    assert "windows of at least 0.2 s" in text.replace("\n", " ")
    assert "not an instantaneous peak" in text.replace("\n", " ")


def test_many_tracks_paginate_and_repeat_headers(tmp_path, report_data):
    path = tmp_path / "many.pdf"
    build_report(replace(report_data, players=[player(i) for i in range(1, 181)]), path)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    assert len(pages) > 8
    assert "Track 180" in "\n".join(pages)
    assert sum("Effective" in text and "Sprints" in text for text in pages) >= 5
    assert all(len(text) > 100 for text in pages)


@pytest.mark.parametrize("missing", ["players", "teams", "both"])
def test_partial_families_are_explicit(tmp_path, report_data, missing):
    changes = {name: None for name in ("players", "teams") if missing in (name, "both")}
    path = tmp_path / "partial.pdf"
    build_report(replace(report_data, **changes), path)
    text = " ".join(page.extract_text() for page in PdfReader(path).pages)
    if "players" in changes:
        assert "no current player analytics result" in text and "Track 1" not in text
    if "teams" in changes:
        assert (
            "no current team tactical analytics result" in text
            and "Average width" not in text
        )


def test_heatmap_respects_length_x_width_y(tmp_path, report_data):
    heatmap = TrackHeatmapRead(
        match_id=42,
        video_id=1,
        job_id=2,
        trajectory_job_id=3,
        track_id=1,
        pitch_length_metres=30,
        pitch_width_metres=20,
        bins_x=3,
        bins_y=2,
        total_occupancy_seconds=0.1,
        cells=[
            HeatmapCell(
                track_id=1,
                x_bin=2,
                y_bin=0,
                x_min=20,
                x_max=30,
                y_min=0,
                y_max=10,
                occupancy_seconds=0.1,
                occupancy_fraction=1,
            )
        ],
    )
    graphic = heatmap_drawing(heatmap)
    cell = [shape for shape in graphic.contents if isinstance(shape, Rect)][1]
    scale = 445 / 30
    assert cell.x == pytest.approx(30 + 20 * scale)
    assert cell.y == pytest.approx(35 + 10 * scale)  # Y=0 occupies the TOP half.
    path = tmp_path / "heatmap.pdf"
    build_report(replace(report_data, heatmaps=[heatmap]), path)
    assert "pitch occupancy" in " ".join(
        page.extract_text() for page in PdfReader(path).pages
    )


@pytest.mark.parametrize("payload", [b"", b"not a PDF", b"%PDF-1.4" + b"x" * 100])
def test_reject_invalid_pdf(tmp_path, payload):
    path = tmp_path / "bad.pdf"
    path.write_bytes(payload)
    with pytest.raises((ValueError, PdfReadError)):
        validate_pdf(path)


def test_reject_truncated_pdf(tmp_path, report_data):
    path = tmp_path / "truncated.pdf"
    build_report(report_data, path)
    path.write_bytes(path.read_bytes()[:-12])
    with pytest.raises(ValueError, match="Truncated"):
        validate_pdf(path)


@pytest.mark.parametrize(
    "value", ["=SUM(A1)", "+cmd", "-formula", "@cell", "\t =formula"]
)
def test_spreadsheet_text_escaped(value):
    assert csv_cell(value) == "'" + value


def test_csv_numeric_null_and_nonfinite():
    assert csv_cell(-3.25) == -3.25
    assert csv_cell(None) == ""
    for value in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(DomainError, match="invalid numerical"):
            csv_cell(value)


def test_duration_rounding_carries_at_minute_boundary():
    assert duration(59.96) == "1:00.0"
    assert duration(60.01) == "1:00.0"
    assert duration(0.1) == "0:00.1"
    assert duration(None) == "Unavailable"


def test_publication_collision_preserves_unowned_destination(settings):
    artifact = ReportArtifact(settings, 1, 2, 3, 0)
    artifact.path.parent.mkdir(parents=True)
    artifact.path.write_bytes(b"previous published report")
    with pytest.raises(FileExistsError), artifact:
        artifact.temporary.write_bytes(b"new attempt")
        artifact.publish()
    assert artifact.path.read_bytes() == b"previous published report"
    assert not artifact.temporary.exists()
