# FOOTLYTICS KPI catalogue

Every metric that the implemented system produces, how it is calculated and where
it appears. Branch `feature/kpi-quality`; findings, fixes and measured comparisons
are in [KPI_QUALITY_REPORT.md](KPI_QUALITY_REPORT.md).

## Conventions

- **Pitch coordinates** are metres on the match's own pitch: X along the length
  (0..L), Y along the width (0..W). A player's ground point is the bounding-box
  bottom centre `((x1 + x2) / 2, y2)`, mapped by the saved homography.
- **Track ID** is a match-specific ByteTrack identity. It is never a named roster
  player, and one real player can appear as several Track IDs.
- **Type** distinguishes a *measurement* (a physical or geometric quantity with
  units) from a *diagnostic* (a count or quality indicator about processing).
  No diagnostic is an accuracy score, and no measurement here has been validated
  against independent football ground truth (see each "Validation" entry).
- **Unavailable** values are `null` in the API and "—" or "Unavailable" in the UI,
  PDF and CSV. One schema-fixed exception: a track with no measured movement
  window has `total_distance_metres` and sprint totals of 0 together with
  `active_duration_seconds` 0 and `valid_interval_count` 0 in the API and CSV; the
  UI and PDF show these as unavailable rather than as a measured zero.
- Defaults below are the deployed configuration: `.env` overrides only
  `YOLO_MODEL`, `YOLO_CONFIDENCE=0.25` and `DEVICE=auto`.

### Processing graph and currentness

```
video → preparation → calibration → detection → tracking ┬→ team classification ─────────────┐
                                                          └→ coordinate mapping → trajectory  │
                                                             cleaning → player analytics      │
                                         trajectory cleaning + effective teams → team tactics ┘
                         player analytics + team tactics + assignments → PDF report and CSVs
```

Each stage is a separate RQ job whose saved summary records the exact upstream
job, attempt and calibration version. A reader returns `409` ("stale") when any
upstream identity no longer matches; nothing is recalculated on read.

## 1. Player performance (per Track ID)

Source: Phase 10 cleaned trajectories (`usable` rows only). Implementation:
`backend/app/analytics/player.py` (`calculate_players`, `_track`). Job:
`player_analytics` (requires current trajectory cleaning). API:
`GET /api/matches/{id}/player-analytics` (paginated) and `/{track_id}`. UI:
Match Analytics → Players (table and track details) and Overview. CSV:
`player-analytics.csv`. PDF: "Player analytics" table.

**Movement window.** Movement is measured between observations at least
`PLAYER_SPEED_WINDOW_SECONDS` (default **0.2 s**) apart within one continuous run
(consecutive valid usable observations of one cleaned segment). The run's
remainder extends the last window; a run shorter than the window gives no
movement measurement. `0` restores the original every-consecutive-pair method.
Results record `speed_window_seconds` and `method` (`minimum_time_windows_v2`,
or `consecutive_clean_intervals_v1` for results saved before this change).

| KPI (field) | Formula and units | Type | UI / PDF / CSV | Validation | Limitation / status |
| --- | --- | --- | --- | --- | --- |
| Total distance (`total_distance_metres`) | Σ straight-line displacement between window endpoints, metres | Measurement | Players "Distance"; PDF "Distance (m)"; CSV | Unit tests with hand-calculated paths; synthetic known-truth paths with measured noise | Fixed in this branch: per-frame jitter inflated distance (+21% on the real clip). Corner-cutting ≈ −1.6% at sharp 90° turns. No real-world ground truth |
| Active duration (`active_duration_seconds`) | Σ window durations, seconds | Measurement | Players "Active duration"; PDF; CSV | Unit tests | Observed sampled time, not minutes played; runs shorter than the window are excluded |
| Average speed (`average_speed_mps`, `_kmh`) | distance / active duration; km/h = m/s × 3.6; `null` when duration is 0 | Measurement | Players "Average speed" (km/h); PDF; CSV (both units) | Unit tests (units, irregular time, null) | Same noise and coverage limits as distance |
| Maximum speed (`max_speed_mps`, `_kmh`) | Fastest movement window (≥ 0.2 s); `null` when no window | Measurement | Players "Maximum speed"; PDF "Max speed (km/h)"; CSV | Unit tests; synthetic peak error | Fixed in this branch: per-frame maxima were noise-dominated. It is a ≥ 0.2 s average, not an instantaneous peak |
| Sprint count (`sprint_count`) | Consecutive windows with speed ≥ 7 m/s whose total duration ≥ 1 s (inclusive) | Measurement (event count) | Players "Sprints"; Overview "Tracks with sprints"; PDF; CSV | Unit tests (threshold inclusivity, separate events, breaks at rejections/segments/gaps) | Thresholds configurable (`PLAYER_SPRINT_SPEED_THRESHOLD_MPS`, `PLAYER_SPRINT_MIN_DURATION_SECONDS`); fragmented tracks can split a real sprint |
| Sprint distance (`sprint_distance_metres`) | Σ window distance inside qualifying sprints, metres | Measurement | Players "Sprint distance"; PDF "Sprint dist. (m)"; CSV | Unit tests | As above |
| Sprint duration (`sprint_duration_seconds`) | Σ window duration inside qualifying sprints, seconds | Measurement | Track details; CSV | Unit tests | As above |
| Observed coverage (`observed_coverage_percent`) | 100 × active duration / source video duration; `null` if duration unknown or inconsistent | Diagnostic | Track details, heatmap; Overview "Partially observed" | Unit test (`test_observation_coverage.py`) | Coverage of measured movement, not of the player's match |
| Coverage warning (`coverage_warning`) | < 15 s observed → short fragment; else < 20% → low coverage | Diagnostic | Track details, heatmap | Unit test | Display caution, not a quality score |
| Usable observations (`usable_observation_count`) | Count of usable cleaned rows | Diagnostic | Track details | Unit tests | — |
| Valid movement windows (`valid_interval_count`) | Count of measured windows | Diagnostic | Track details | Unit tests | Fewer than observations by design (≈ 5 frames per window at 25 FPS) |
| Excluded intervals (`excluded_interval_count`) | Consecutive pairs failing dt ∈ (0, max gap], speed ≤ max plausible, increasing frame | Diagnostic | Track details; job warning | Unit tests | Limits come from the saved cleaning run (12 m/s, 2 s) |
| Movement segments (`segment_count`) | Distinct cleaned segments containing usable rows | Diagnostic | Track details | Unit tests | Full-cadence cleaning splits on bounding-box jumps (see report) |
| Observation extents (`first_/last_frame`, `first_/last_timestamp`) | Min/max over usable rows | Diagnostic | Track details | Unit tests | — |

Run-level summary (`analytics_summary` on the job): source/usable/rejected rows,
unique tracks, valid/excluded intervals, sprint events, heatmap cells, the saved
thresholds, `speed_window_seconds` and `method`.

## 2. Heatmaps (per Track ID)

Implementation: `backend/app/analytics/heatmaps.py` (`OccupancyGrid`), filled by
`_track` with each window's duration in the cell of its **start** position. Job:
`player_analytics`. API: `GET /api/matches/{id}/player-analytics/{track}/heatmap`.
UI: Analytics → Heatmap (pitch-scaled cells, legend, most occupied cells). PDF:
up to `REPORT_HEATMAP_LIMIT` (4) tracks with movement, chosen by Track ID order.

| KPI (field) | Formula and units | Type | Validation | Limitation / status |
| --- | --- | --- | --- | --- |
| Occupancy seconds (`cells[].occupancy_seconds`) | Σ window durations starting in the cell, seconds | Measurement | Unit tests (match grid, interval start, maximum boundary) | Sparse: only cells with time are returned |
| Occupancy fraction (`occupancy_fraction`) | cell seconds / track active duration, ≤ 1 | Measurement | Unit tests | Relative to the observed time only |
| Total occupancy (`total_occupancy_seconds`) | = active duration; the API rejects a bundle whose cells do not sum to it | Measurement | Service consistency check | — |
| Grid resolution (`bins_x` × `bins_y`, cell bounds) | 20 × 12 by default; cell = L/20 × W/12 m (5.25 × 5.67 m on 105 × 68 m) | Configuration | Unit tests | A boundary point belongs to the last cell; the cell index (not the coordinate) is clamped |
| Most occupied cells (UI) | Backend cells sorted by occupancy seconds | Presentation | Frontend tests | Order only; no values are changed |

## 3. Team tactics (per frame snapshot and per team)

Source: cleaned usable positions grouped by frame plus **effective** team labels
(manual override, otherwise classifier result; Unknown excluded).
Implementation: `backend/app/analytics/team.py` (`snapshot`, `Aggregate`,
`calculate_teams`). Job: `team_tactical_analytics` (requires current trajectories
and the exact effective assignment fingerprint). API:
`GET /api/matches/{id}/team-analytics` and `/{team}/series` (paginated by frame).
UI: Analytics → Team Tactics (data basis, comparison, centroid paths, time
series). CSV: `team-analytics.csv`. PDF: "Team tactical analytics" table.

A snapshot is **valid** when the team has at least `TACTICS_MIN_PLAYERS_PER_TEAM`
(3) usable positions in that frame; otherwise only `visible_players` is kept.
Summary averages are arithmetic means over that team's valid snapshots where the
metric exists (`null` when none).

| KPI (snapshot field / summary field) | Formula and units | Type | Validation | Limitation |
| --- | --- | --- | --- | --- |
| Visible players (`visible_players` / `avg_visible_players`) | Usable assigned positions in the frame; average over **valid** snapshots | Diagnostic | Unit tests | Visible in camera and tracked, not players on the pitch |
| Centroid (`centroid_x/y` / `avg_centroid_x/y`) | Mean X and mean Y, metres | Measurement | Unit tests (hand-calculated) | Visible subset only |
| Width (`width_metres` / `avg_width_metres`) | max Y − min Y, metres | Measurement | Unit tests | Visible subset only |
| Depth (`depth_metres` / `avg_depth_metres`) | max X − min X, metres | Measurement | Unit tests | No attacking direction is inferred |
| Compactness radius (`compactness_radius_metres`) | Mean Euclidean distance to the centroid, metres | Measurement | Unit tests | Descriptive, not tactical quality |
| Player spacing (`mean_pairwise_distance_metres` / `avg_pairwise_distance_metres`) | Mean distance over all n(n−1)/2 pairs, metres | Measurement | Unit tests | — |
| Convex hull area (`convex_hull_area_m2` / `avg_convex_hull_area_m2`) | OpenCV convex hull area, m²; `null` if collinear | Measurement | Unit tests (degenerate cases) | `hull_snapshots` counts its denominator |
| Bounding-box area (`bounding_box_area_m2` / `avg_bounding_box_area_m2`) | width × depth, m² | Measurement | Unit tests | — |
| Centroid separation (`centroid_distance_to_opponent_metres`) | Distance between both teams' centroids when both snapshots are valid | Measurement | Unit tests | `both_teams_valid_snapshots` counts its denominator |
| Valid / insufficient snapshots | Counts per team; valid + insufficient = observed frames | Diagnostic | Unit tests; API consistency check | — |
| Data basis (`observed_frames`, `usable_rows`, `assigned_rows`, `unknown_rows`, `rejected_rows`) | Row and frame counts | Diagnostic | Unit tests | Unknown tracks are excluded from geometry |
| Time series (`/series`) | One row per team per observed frame, frame order, actual timestamps | Measurement series | Unit tests; frontend tests | Frames with no usable observation produce no row; the UI breaks centroid paths there (this branch) |

## 4. Computer vision and processing metrics

| KPI | Definition | Implementation / endpoint | Type | Validation |
| --- | --- | --- | --- | --- |
| Processed frames | Frames with `frame % DETECTION_FRAME_STRIDE == 0` | `cv/pipeline.py`; detection/tracking review summaries | Diagnostic | Tests |
| Reported detections | Person boxes with confidence ≥ `YOLO_CONFIDENCE` (0.25) inside the pitch ROI when available | `cv/pipeline.py`; `DetectionSummary.total_detections` | Diagnostic | SoccerNet-GSR precision/recall (see report) |
| Average detections per frame | reported detections / processed frames | review summary | Diagnostic | — |
| Low-confidence candidates | Boxes in [`TRACK_LOW_THRESH`, `YOLO_CONFIDENCE`) kept only for ByteTrack's second association | `DetectionSummary.low_confidence_detections` | Diagnostic | — |
| Unique tracks | Distinct ByteTrack IDs | `TrackingSummary.unique_tracks` | Diagnostic | SoccerNet IDF1/MOTA/ID switches (see report) |
| Tracked observations / average visible tracks per frame | Track rows; rows / processed frames | review summary | Diagnostic | — |
| Mapped / invalid boxes | `valid_mapped_rows`, `skipped_invalid_boxes` | `cv/coordinate_pipeline.py`; `/coordinates/summary` | Diagnostic | Tests |
| Inside / outside pitch | Mapped ground point within [0, L] × [0, W] (±1 µm) | `cv/player_position.py` | Diagnostic | Tests; never clamped |
| Calibration reprojection error | Mean Euclidean pitch distance between mapped image points and their pitch landmarks, metres | `cv/homography.py`; calibration API | Diagnostic | Fitting residual only; **not** independent accuracy |
| Trajectory statuses | `accepted`, `smoothed`, `segment_start`, `outside_pitch`, `jump_outlier`, `invalid_temporal`; usable = first three | `cv/trajectory.py`; `/trajectories/summary` | Diagnostic | Tests |
| Team labels | `automatic_team`, `manual_team`, `effective_team` (Team A / Team B / Unknown) | `cv/team_classifier.py`; `/team-assignments` | Classification | SoccerNet-GSR team coverage/accuracy (see report) |
| Classification confidence | Automatic: product of sample quality, cluster separation, margin and closeness. User-seeded (`seeded_separable_votes_v2`): share of the track's crops that clearly voted for the assigned kit (≤ ½ the distance to the other prototype, ≤ 25 Lab units, ≥ 50% coherent pixels; ≥ 3 votes, none opposing) | `TeamAssignmentRead.automatic_confidence`, provenance | Diagnostic score, not a probability | SoccerNet-GSR (see report) |
| Classification diagnostics | Attempted/rejected crops, insufficient or inconsistent tracks, eligible tracks, low-margin tracks, median sample quality and samples per track, cluster separation (Lab) | `ClassificationSummary.diagnostics` | Diagnostic | — |
| Job status, stage, progress, warnings, attempts | Durable `ProcessingJob` fields; retries advance the attempt | `/jobs`, `/jobs/{id}` | Diagnostic | Job tests |
| Tracking continuity (evaluation only) | Track spans, short tracks, observed track-seconds | `app/evaluation/continuity.py`, `scripts/evaluate_continuity.py` | Diagnostic proxy | Not IDF1 without ground truth |

## 5. Dashboard

Totals are the `total` of the scoped list endpoints (`/clubs`, `/teams`,
`/players`, `/matches` with `limit=1`), so each user sees only records the
backend's club-scope rules allow. "Latest matches" lists the five newest matches;
"Processing" counts the latest job of each of those five matches (active, failed,
completed with warnings, completed, cancelled, no job) and is labelled as such.
Implementation: `frontend/src/pages/FoundationPage.tsx`,
`frontend/src/features/dashboard/`. Type: diagnostic counts.

## 6. Reports and exports

The PDF (`/report/file`) and both CSVs (`/exports/*.csv`) read the same saved,
current player-analytics and team-tactics bundles as the API; they never
recalculate. The PDF methodology section prints the saved sprint thresholds and
speed window. CSV text cells are protected against formula injection without
altering signed numbers. Columns:

- `player-analytics.csv`: `track_id, effective_team, total_distance_metres,
  active_duration_seconds, average_speed_mps, average_speed_kmh, max_speed_mps,
  max_speed_kmh, sprint_count, sprint_distance_metres, sprint_duration_seconds`
- `team-analytics.csv`: `team, valid_snapshots, insufficient_snapshots,
  avg_visible_players, avg_centroid_x, avg_centroid_y, avg_width_metres,
  avg_depth_metres, avg_compactness_radius_metres, avg_pairwise_distance_metres,
  hull_snapshots, avg_convex_hull_area_m2, avg_bounding_box_area_m2,
  both_teams_valid_snapshots, avg_centroid_distance_to_opponent_metres`

## Count

57 implemented KPIs and indicators: 13 player, 5 heatmap, 14 team-tactics,
19 computer-vision/processing and 6 dashboard. Measurements: distance, active
duration, average and maximum speed, the three sprint metrics, heatmap occupancy,
and the eight team-geometry metrics with their averages. Everything else is a
diagnostic count, a quality indicator or configuration.
