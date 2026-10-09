"""A4 presentation of saved analytics. No CV or metric computation lives here."""

from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from app.reports.data import ReportData
from app.schemas.player_analytics import TrackHeatmapRead

INK = colors.HexColor("#173449")
ACCENT = colors.HexColor("#16786e")
PALE = colors.HexColor("#edf4f6")
TEAM_NAMES = {"team_a": "Team A", "team_b": "Team B", "unknown": "Unknown"}
SECTIONS = [
    "Match information",
    "Executive summary",
    "Player analytics",
    "Team tactical analytics",
    "Methodology and limitations",
]


def team_label(assignments: dict[int, str] | None, track_id: int) -> str:
    return (
        "Unavailable"
        if assignments is None
        else TEAM_NAMES.get(assignments.get(track_id, "unknown"), "Unknown")
    )


def number(
    value: float | int | None,
    suffix: str = "",
    digits: int = 1,
    *,
    missing: str = "Unavailable",
) -> str:
    return missing if value is None else f"{value:,.{digits}f}{suffix}"


def duration(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    # Preserve short measured durations; only presentation is rounded.
    minutes, tenths = divmod(round(value * 10), 600)
    return f"{minutes}:{tenths / 10:04.1f}"


def heatmap_drawing(heatmap: TrackHeatmapRead) -> Drawing:
    length, width = heatmap.pitch_length_metres, heatmap.pitch_width_metres
    scale = min(445 / length, 320 / width)
    left, bottom = 30, 35
    drawing = Drawing(505, width * scale + 70)
    drawing.add(
        Rect(
            left, bottom, length * scale, width * scale, fillColor=PALE, strokeColor=INK
        )
    )
    maximum = max((cell.occupancy_fraction for cell in heatmap.cells), default=1)
    for cell in heatmap.cells:
        intensity = cell.occupancy_fraction / maximum
        color = colors.Color(
            0.86 - 0.77 * intensity, 0.94 - 0.48 * intensity, 0.93 - 0.49 * intensity
        )
        # PDF coordinates rise upwards. Pitch Y rises downwards from the top left.
        drawing.add(
            Rect(
                left + cell.x_min * scale,
                bottom + (width - cell.y_max) * scale,
                (cell.x_max - cell.x_min) * scale,
                (cell.y_max - cell.y_min) * scale,
                fillColor=color,
                strokeColor=None,
            )
        )
    drawing.add(
        Rect(
            left, bottom, length * scale, width * scale, fillColor=None, strokeColor=INK
        )
    )
    drawing.add(
        Line(
            left + length * scale / 2,
            bottom,
            left + length * scale / 2,
            bottom + width * scale,
            strokeColor=INK,
        )
    )
    drawing.add(
        String(
            left,
            bottom + width * scale + 12,
            "(0, 0) — X right; Y down",
            fontName="ReportRegular",
            fontSize=9,
        )
    )
    drawing.add(
        String(
            left,
            15,
            f"X: pitch length {length:g} m   |   Y: pitch width {width:g} m",
            fontName="ReportRegular",
            fontSize=9,
        )
    )
    return drawing


def build_report(data: ReportData, path: Path) -> list[str]:
    """Fixed ordering, timestamp input, embedded fonts and invariant PDF metadata."""
    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (("ReportRegular", "Vera.ttf"), ("ReportBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    styles = getSampleStyleSheet()
    for name in ("Normal", "BodyText", "Heading1", "Heading2", "Title"):
        styles[name].fontName = (
            "ReportBold"
            if name.startswith("Heading") or name == "Title"
            else "ReportRegular"
        )
        styles[name].textColor = INK
    styles["BodyText"].fontSize, styles["BodyText"].leading = 10, 15
    styles["Heading1"].fontSize, styles["Heading1"].leading = 18, 23
    styles.add(
        ParagraphStyle(
            "Cell", fontName="ReportRegular", fontSize=8.5, leading=11, textColor=INK
        )
    )
    styles.add(
        ParagraphStyle(
            "HeaderCell",
            parent=styles["Cell"],
            fontName="ReportBold",
            textColor=colors.white,
        )
    )
    story = []

    def p(text: object, style: str = "BodyText") -> Paragraph:
        # Match names are plain text; never permit Paragraph HTML/image execution.
        return Paragraph(escape(str(text)), styles[style])

    def heading(text: str) -> None:
        story.extend([Spacer(1, 10), p(text, "Heading1")])

    def table(
        headers: list[str], rows: list[list], widths: list[float] | None = None
    ) -> None:
        cells = [[p(item, "HeaderCell") for item in headers]]
        cells.extend([[p(value, "Cell") for value in row] for row in rows])
        item = LongTable(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, ACCENT),
                ]
            )
        )
        story.append(item)

    meta = data.metadata
    timestamp = data.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    story.extend(
        [
            p("FOOTLYTICS", "Title"),
            p("Match Analytics Report", "Heading1"),
            p(meta["title"], "Heading2"),
        ]
    )
    table(
        ["Match information", "Recorded value"],
        [
            ["Match", f"Match {meta['match_id']} · {meta['match_format']}"],
            ["Team A", meta["team_a"]],
            ["Team B", meta["team_b"]],
            ["Club", meta["club"]],
            ["Match date", meta["match_date"] or "Unavailable"],
            *([["Venue", meta["venue"]]] if meta["venue"] else []),
            [
                "Pitch",
                f"{meta['pitch_length_metres']:g} m length (X) × "
                f"{meta['pitch_width_metres']:g} m width (Y)",
            ],
            ["Generated", timestamp],
        ],
        [125, 386],
    )
    heading("Executive summary")
    if data.players is None:
        story.append(
            p("Player analytics: Unavailable. " + data.unavailable.get("players", ""))
        )
    else:
        story.append(
            p(
                f"Analyzed tracks: {len(data.players)}. Track IDs identify tracks "
                "within this Match, not named roster players."
            )
        )
        if data.assignments is None:
            story.append(p("Effective team assignments: Unavailable."))
        else:
            counts = {
                team: sum(
                    team_label(data.assignments, row.track_id) == team
                    for row in data.players
                )
                for team in TEAM_NAMES.values()
            }
            story.append(
                p(
                    "Analyzed track assignments: "
                    + "; ".join(f"{label}: {count}" for label, count in counts.items())
                    + "."
                )
            )
    if data.teams is None:
        story.append(
            p(
                "Team tactical analytics: Unavailable. "
                + data.unavailable.get("tactics", "")
            )
        )
    else:
        story.append(
            p(
                "Valid tactical snapshots: "
                + "; ".join(
                    f"{TEAM_NAMES[row.team]}: {row.valid_snapshots}"
                    for row in data.teams
                )
                + "."
            )
        )
    story.append(
        p(
            "This report describes published observations. It does not rank "
            "players or infer tactical superiority."
        )
    )

    story.append(PageBreak())
    heading("Player analytics")
    story.append(
        p(
            "Distance is measured on usable cleaned trajectory intervals. "
            "Duration is active sampled duration (minutes:seconds), not video "
            "time or minutes played."
        )
    )
    story.append(
        p(
            "A dash (—) means unavailable, including distance and sprints for "
            "tracks without a measured movement window."
        )
    )
    if data.players is None:
        story.append(p("Unavailable — no current player analytics result."))
    elif not data.players:
        story.append(p("No analyzed tracks in the current result."))
    else:
        table(
            [
                "Track",
                "Effective team",
                "Distance (m)",
                "Active duration",
                "Avg speed (km/h)",
                "Max speed (km/h)",
                "Sprints",
                "Sprint dist. (m)",
                "Sprint duration",
            ],
            [
                [
                    f"Track {row.track_id}",
                    team_label(data.assignments, row.track_id),
                    *(
                        [
                            number(row.total_distance_metres),
                            duration(row.active_duration_seconds),
                            number(row.average_speed_kmh, missing="—"),
                            number(row.max_speed_kmh, missing="—"),
                            str(row.sprint_count),
                            number(row.sprint_distance_metres),
                            duration(row.sprint_duration_seconds),
                        ]
                        if row.valid_interval_count
                        # No measured movement window: zeros are not measurements.
                        else [
                            "—",
                            duration(row.active_duration_seconds),
                            "—",
                            "—",
                            "—",
                            "—",
                            "—",
                        ]
                    ),
                ]
                for row in data.players
            ],
            [59, 60, 55, 55, 59, 59, 51, 57, 56],
        )
    story.append(PageBreak())
    heading("Team tactical analytics")
    story.append(
        p(
            "Visible team geometry only. Width = Y-axis range; depth = X-axis "
            "range. Values are averages over valid snapshots, with optional "
            "metrics using their own reported coverage."
        )
    )
    if data.teams is None:
        story.append(p("Unavailable — no current team tactical analytics result."))
    else:
        by_team = {row.team: row for row in data.teams}
        metrics = [
            ("Valid snapshots", "valid_snapshots", "", 0),
            ("Insufficient snapshots", "insufficient_snapshots", "", 0),
            ("Average visible players", "avg_visible_players", "", 1),
            ("Average centroid X", "avg_centroid_x", " m", 1),
            ("Average centroid Y", "avg_centroid_y", " m", 1),
            ("Average width (Y range)", "avg_width_metres", " m", 1),
            ("Average depth (X range)", "avg_depth_metres", " m", 1),
            ("Compactness radius", "avg_compactness_radius_metres", " m", 1),
            ("Average pairwise spacing", "avg_pairwise_distance_metres", " m", 1),
            ("Convex hull / footprint area", "avg_convex_hull_area_m2", " m²", 1),
            ("Hull snapshots", "hull_snapshots", "", 0),
            ("Bounding box area", "avg_bounding_box_area_m2", " m²", 1),
            (
                "Between-team centroid separation",
                "avg_centroid_distance_to_opponent_metres",
                " m",
                1,
            ),
            ("Both teams valid snapshots", "both_teams_valid_snapshots", "", 0),
        ]
        table(
            ["Published metric", "Team A", "Team B"],
            [
                [
                    label,
                    *[
                        number(getattr(by_team[team], field), unit, digits)
                        for team in ("team_a", "team_b")
                    ],
                ]
                for label, field, unit, digits in metrics
            ],
            [245, 133, 133],
        )

    for heatmap in data.heatmaps:
        story.append(PageBreak())
        heading(f"Track {heatmap.track_id} — pitch occupancy")
        story.append(
            p(
                f"{team_label(data.assignments, heatmap.track_id)}. Saved Phase 11 "
                "occupancy; darker cells show a greater share of this track's "
                "active duration. Unobserved cells have no recorded occupancy."
            )
        )
        story.extend([Spacer(1, 16), heatmap_drawing(heatmap), Spacer(1, 12)])
        story.append(
            p(
                "Recorded occupancy duration: "
                f"{duration(heatmap.total_occupancy_seconds)}. "
                f"Cells: {heatmap.bins_x} × {heatmap.bins_y}."
            )
        )
        story.append(
            p(
                f"Detail pages show at most {data.heatmap_limit} tracks with "
                "usable duration, ordered by Track ID. "
                "This selection is not a performance ranking."
            )
        )

    story.append(PageBreak())
    heading("Methodology and limitations")
    story.append(
        p(
            "Recorded Match video > YOLO player detection > ByteTrack tracking > "
            "jersey-based team assignment > pitch calibration / homography > "
            "bounding-box bottom-centre ground point > cleaned pitch trajectories "
            "> player analytics > team spatial analytics."
        )
    )
    story.append(
        p(
            "This report reads saved Phase 11 and Phase 12 outputs and effective "
            "team assignments. It does not rerun processing or recalculate metrics. "
            "Pitch coordinates are metres: X is length; Y is width."
        )
    )
    if data.sprint_threshold_mps is not None:
        story.append(
            p(
                "Published sprint settings: threshold "
                f"{data.sprint_threshold_mps:g} m/s; minimum duration "
                f"{data.sprint_min_duration_seconds:g} s. "
                "These thresholds are configurable."
            )
        )
    if data.speed_window_seconds is not None:
        story.append(
            p(
                "Distance and speeds use straight-line displacement over movement "
                f"windows of at least {data.speed_window_seconds:g} s; maximum speed "
                "is the fastest such window, not an instantaneous peak."
                if data.speed_window_seconds
                else "Distance and speeds use every consecutive observation pair; "
                "maximum speed is the fastest such interval."
            )
        )
    for limitation in [
        "Track IDs are Match-specific and are not automatically named roster players.",
        "Occlusion and visibility changes can cause tracking errors and ID switches.",
        "Calibration quality and camera motion affect physical position accuracy.",
        "Missing movement cannot be recovered; sampled trajectories may "
        "underestimate real distance.",
        "Sprint thresholds are configurable; results inherit upstream "
        "processing and analytics accuracy.",
        "Tactical metrics describe visible geometry. Unknown team labels "
        "reduce tactical coverage.",
        "Attacking direction, formations and player performance rankings "
        "are not inferred.",
        "No ball or event analytics, possession, passes, shots or xG are included.",
        "Unavailable analytics remain unavailable. This is a descriptive report, "
        "not an automated coaching judgment.",
        "A stored report is a snapshot. Regenerate after relevant metadata, "
        "assignments or analytics change.",
    ]:
        story.append(p("• " + limitation))
    if data.source_jobs:
        story.append(
            p(
                "Published sources: "
                + "; ".join(
                    f"{label} job {job_id}"
                    for label, job_id in data.source_jobs.items()
                )
                + "."
            )
        )

    def footer(canvas: Canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.line(42, 39, A4[0] - 42, 39)
        canvas.setFont("ReportRegular", 8)
        canvas.setFillColor(INK)
        canvas.drawString(
            42, 25, f"FOOTLYTICS · Match {meta['match_id']} · {timestamp}"
        )
        canvas.drawRightString(A4[0] - 42, 25, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=42,
        bottomMargin=54,
        title=f"FOOTLYTICS Match {meta['match_id']} Analytics",
        author="FOOTLYTICS",
        pageCompression=1,
        invariant=1,
    )
    document.build(
        story,
        onFirstPage=footer,
        onLaterPages=footer,
    )
    return [*SECTIONS, *(["Player heatmaps"] if data.heatmaps else [])]
