# FOOTLYTICS KPI quality report

Branch `feature/kpi-quality` (from the approved UI redesign, `3f54122`). Every KPI
is catalogued in [KPI_CATALOG.md](KPI_CATALOG.md). This report records what was
reviewed, what was wrong, what changed, what was tried and rejected, and what is
still limited. All numbers come from runs on this workstation (WSL2, Intel
i5-1250P, CPU only, YOLO11n); evidence paths are listed under
[Reproduction](#reproduction).

Evidence is labelled by kind and never mixed:

- **[Math]** correctness shown by deterministic unit tests with hand-calculated values;
- **[Integration]** repeatability shown by end-to-end runs on the same inputs;
- **[GT]** accuracy against independent human annotations (SoccerNet-GSR);
- **[Synthetic]** estimator behaviour on analytic paths with known truth;
- **[Qualitative]** observation without ground truth.

## Summary of KPI changes

| KPI | Problem | Root cause | Code change | Before | After | Verification | Remaining limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Total distance, average speed | Inflated at full frame rate | Each 0.04 s step adds bounding-box jitter (σ ≈ 2 cm X, 5 cm Y) to the path length | `PLAYER_SPEED_WINDOW_SECONDS` (0.2 s): displacement between window endpoints; `analytics/player.py` | Real clip, same tracks: 25 Hz pooled speed 2.90 m/s vs 2.40 m/s at 5 Hz (+21%) | 2.30 vs 2.40 m/s; same-track ratio 1.21 → 0.98 | [Math] 5 new tests; [Synthetic] walking error +8.4% → +1.0%; [Integration] cadence agreement | −1.6% at sharp 90° turns; runs < 0.2 s not measured (−5.5% active time at 25 Hz) |
| Maximum speed | Noise-dominated | Fastest single 0.04 s interval | Fastest ≥ 0.2 s window; UI/PDF state the basis | Per-track median 8.08 m/s; 36 tracks ≥ 10 m/s | 4.43 m/s; 0 tracks ≥ 10 m/s (5 Hz: 4.33, 1) | [Synthetic] jog peak 5.24 → 3.91 (true 3.5) | A 0.2 s average, not an instantaneous peak |
| Sprints, time above threshold | Noise both creates and breaks threshold runs | Per-frame speeds | Same windowed speeds | 5.2% of time ≥ 7 m/s | 0.61% (5 Hz: 1.15%) | [Math] ≥ 1 s of qualifying windows; [Synthetic] sprint 1/1, short burst 0/0 | No real sprint ground truth; fragmented tracks can split sprints |
| Detection precision/recall (evaluation) | Precision 76.7% reported for current code | Evaluator scored ByteTrack-only low-score candidates (0.10–0.25) as detections | `evaluation/detection.py` scores reported boxes (≥ `YOLO_CONFIDENCE`) | P 76.7%, R 90.2% | P 88.6%, R 85.4% (identical to Phase 15) | [Math] new test; Phase 15 rescoring unchanged | — |
| Team labels (user-seeded) | 3 of 49 identities classified | A crop counted only if quality × separation × margin × closeness ≥ 0.6; typical clear crops scored ≈ 0.46 | Separable per-crop votes (`cv/team_colors.py`) | 6.1% coverage, 3/3 correct | 57.1% coverage, 27/28 correct (96.4%) | [GT] SoccerNet-GSR; [Math] 5 new tests; [Qualitative] 29/29 crops on the 60 s clip | 1 of 4 referees received a team; short tracks stay Unknown |
| Team centroid path (UI) | Could join snapshots across frames with no observation | Frames without usable rows produce no series row | Path breaks when the frame step exceeds the series cadence | Line across the gap | Separate runs | Frontend test | — |
| Unmeasured distance/sprints (UI, PDF) | Showed "0.0 m" and "0" | API/CSV contract stores 0 with zero active time | Shown as "Unavailable"/"—" when no window was measured | 0.0 m | Unavailable | Frontend and PDF tests | API/CSV keep numeric 0 with `active_duration_seconds` 0 |

Investigated and **not** changed (evidence insufficient or negative): detection
inference size, ByteTrack thresholds, automatic team classification, Phase 10
cleaning tolerances and the calibration model. Details below.

## 1. Implemented KPIs

57 KPIs and indicators: 13 player, 5 heatmap, 14 team-tactics, 19
computer-vision/processing and 6 dashboard ([KPI_CATALOG.md](KPI_CATALOG.md)).
Player rows are Track IDs, not named roster players.

## 2. Measurements and diagnostics

Measurements (with units): distance, active duration, average and maximum
speed, sprint count/distance/duration, heatmap occupancy and fraction, and team
centroid, width, depth, compactness, pairwise spacing, convex-hull and
bounding-box areas and centroid separation (per snapshot and averaged).
Everything else (counts, coverage, statuses, confidences, reprojection error,
job progress) is a diagnostic. No measurement has independent football ground
truth; detection, tracking and team labels are the only GT-scored outputs.

## 3. Correctness review

Reviewed line by line, with existing tests confirmed: distance as Σ displacement
inside one segment; rejection, segment change and invalid intervals break
continuity; null speeds when no duration; inclusive sprint threshold and minimum
duration; heatmap time at the interval start cell with boundary points in the
last cell; team centroid, width (Y range), depth (X range), compactness, unique
pairwise spacing, degenerate hull → null, averages only over valid snapshots
(`avg_visible_players` included); series ordering and pagination; scoped
dashboard totals; coverage cautions; homography orientation (X length, Y width),
bottom-centre ground point and no clamping.

Defects found and fixed are the seven rows of the summary table. One definition
is documented rather than changed: `avg_visible_players` averages valid
snapshots only.

## 4. Computer-vision comparisons [GT]

SoccerNet-GSR, three clips from three games, 450 frames, 6,603 scored boxes.
Detection is scored at the reported threshold (0.25).

| Configuration | Precision | Recall | F1 | AP50 | IDF1 | MOTA | ID switches | Frames/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Phase 15 (no low-score candidates) | 88.64% | 85.45% | 87.01% | 81.40% | 76.44% | 73.09% | 58 | — |
| Current code, 640 (default) | 88.64% | 85.45% | 87.01% | 81.40% | 75.35% | 73.53% | 57 | 10.53 |
| Inference size 960 | 86.85% | 90.11% | 88.45% | 87.03% | 82.82% | 77.18% | 32 | 7.57 |
| Inference size 1280 | 83.46% | 92.52% | 87.75% | 88.44% | 84.61% | 77.98% | 39 | 5.20 |

960 improved SNGS-021 and SNGS-039 but SNGS-078 lost precision (0.894 → 0.786)
and MOTA (0.692 → 0.654); the evaluation has no pitch ROI, so extra off-pitch
people are a plausible cause, but this was not verified. With inconsistent
per-clip results on three six-second clips and 28% lower throughput, **640
remains the default**; `YOLO_IMAGE_SIZE=960` is a measured option for
1920 × 1080 broadcast footage. Wide panoramas need larger sizes (the development
4096 × 734 clip was processed at 2560).

## 5. Team classification [GT, Qualitative]

SoccerNet-GSR, 49 human team-labelled identities; seeded mode uses the first
frame's labelled outfield crops (up to three per team that pass the production
crop checks), as a user would in Set Team Colors.

| Mode and rule | Classified | Correct among classified | Referees given a team |
| --- | ---: | ---: | ---: |
| Automatic (unchanged) | 4/49 (8.2%) | 4/4 | 0/4 |
| User-seeded, previous rule | 3/49 (6.1%) | 3/3 | 0/4 |
| **User-seeded, separable votes (adopted)** | **28/49 (57.1%)** | **27/28 (96.4%)** | **1/4** |
| User-seeded votes, sampling every 5 frames (not default) | 32/49 (65.3%) | 31/32 (96.9%) | 1/4 |
| Automatic k-means + votes (offline prototype, rejected) | 26/49 (53.1%) | 18/26 (69.2%) | 1/4 |
| Automatic, sampling every 5 frames (rejected) | 3/49 | 1/3 | 0/4 |

Vote parameters were fixed before scoring (ratio 0.5, 25 Lab units, 50% crop
coherence, 3 votes, no opposing vote). Sensitivity: ratio 0.4–0.6, coherence
0.4–0.6 and distance 20–25 all gave 63–65% coverage and 94–97% accuracy among
classified (at 5-frame sampling). Automatic voting was rejected because 2-means
split SNGS-039 by sunlight and shadow rather than by kit (8 confident errors);
sampling every 5 frames is not the default because it harmed automatic mode.

60-second fixed-camera SoccerTrack clip with the user's blue/white seeds (no
ground truth): 3 → 29 of 251 tracks classified at full cadence (9 blue, 20
white), and every one of the 29 crops visually matches its kit; referees in
black and the red goalkeeper stayed Unknown. Coverage is limited by short tracks
(median 0.96 s; 168 under 2 s), which cannot provide three votes.

## 6. Tracking continuity [GT, Integration]

Current production tracking: IDF1 75.35%, MOTA 73.53%, 57 ID switches, 82
fragmentations on SoccerNet. Parameter sweep from cached detections:
`track_buffer` 60/90 slightly worse; `track_match_thresh` 0.7 much worse (IDF1
65.7%); 0.9 better IDF1 (79.1%) with +78 false positives; `track_high_thresh`
0.35 improved every selection clip (IDF1 79.3%) but **not** the confirmation
clips SNGS-022/023 (SNGS-023 IDF1 0.815 → 0.769), so it was rejected. Production
ByteTrack settings are unchanged. The 60-second clip still yields 251 IDs/minute
with a median span of 0.96 s; fragmentation remains the main limit on per-track
KPIs and team coverage. Tracklet stitching stays rejected (hardening record).

## 7. Coordinate validation [Math, GT-like spot check]

Mapping math is covered by existing tests (identity, scaled and projective
mappings, RANSAC with > 4 points, horizon rejection, no clamping). For real
accuracy, standard pitch markings that were **not** fitted were located by eye
on frame 0 of the development clip, whose calibration uses only the four corners
(reprojection residual 2.5 × 10⁻⁶ m):

| Held-out marking | Located with | Error |
| --- | --- | ---: |
| Halfway line × near touchline | high confidence | 1.27 m |
| Centre circle × halfway, near | medium | 2.16 m |
| Centre circle × halfway, far | medium | 4.37 m |
| Left penalty area, near corner | medium | 1.90 m |
| Right penalty area, near corner | medium | 0.92 m |
| Halfway line × far touchline | medium (identity of the line uncertain) | 12.35 m |

Five clearly located markings: mean 2.1 m, range 0.9–4.4 m, growing towards the
far side, where one image row spans about 1.7 m. The clip is a stitched,
curved panorama, which a single planar homography only approximates. Positions,
distances and team geometry from this clip are therefore metre-level
approximations; a near-zero four-point residual is not accuracy. Recommended
mitigation: calibrate with eight or more markings spread across the pitch so the
RANSAC residual becomes informative.

## 8. Distance, speed and sprint correctness

[Math] New tests: stationary jitter (per-pair 0.8 m vs windowed 0 m), remainder
extension (one 0.28 s window, 1.4 m at 5 m/s), runs shorter than the window,
windows never crossing a rejected observation, sprint needing ≥ 1 s of
qualifying windows (1.2 s → 1 sprint of 9.6 m; 0.8 s → none), streaming bounds,
setting validation. Existing tests still pass with the window set to 0.

[Synthetic] Noise matched to the real clip, 30 seeds, 25 Hz (`speed-window-synthetic-v1`):

| Scenario (truth) | Distance error, window 0 → 0.2 s | Max speed, window 0 → 0.2 s | Sprints |
| --- | --- | --- | --- |
| Stationary 10 s (0 m) | 6.02 m → 2.08 m | 2.14 → 0.59 m/s | 0 → 0 |
| Walk 1.5 m/s | +8.40% → +1.05% | 2.81 → 1.78 (1.5) | 0 → 0 |
| Jog on a circle 3.5 m/s | +0.98% → +0.07% | 5.24 → 3.91 (3.5) | 0 → 0 |
| 90° zigzag 4 m/s | −0.57% → −1.60% | 5.60 → 4.39 (4.0) | 0 → 0 |
| Sprint profile, peak 8.5 m/s (1 sprint) | +1.11% → +0.13% | 9.10 → 8.65 | 1 → 1 |
| 0.6 s burst at 7.5 m/s (no sprint) | +1.67% → +0.17% | 8.04 → 7.58 | 0 → 0 |

With twice the noise, per-pair walking distance error reaches +30% (window 0.2:
+4.3%) and per-pair sprint detection drops to 0.77 (window: 0.97); the window
then under-reads the sprint path by 4% because full-cadence cleaning splits runs.
Windows of 0.32–0.4 s cut corners (−6% at sharp turns), so 0.2 s was chosen. At
30 FPS the window behaves as at 25 FPS (walking +1.1%, sprint 1/1); at 50 FPS
cleaning's per-frame plausibility limit (12 m/s × 0.02 s = 0.24 m) splits fast
runs, so the sprint path under-reads by 7% and is detected in only 37% of seeds.

**Rejected: a noise tolerance in cleaning.** Allowing 12 m/s × dt + 0.25 m
(≈ 3σ of measured frame noise) brought the synthetic 50 FPS cases in line with
25 FPS at the measured noise level (walking +1.0%, sprint path +0.2%, sprint
detected in every seed), but on the real clip it admitted persistent ≈ 0.5 m bounding-box jumps:
same-track speed ratio 0.98 → 1.10, tracks ≥ 10 m/s 0 → 5.
Real position errors are heavier-tailed than Gaussian noise, so the conservative
split stays. For 50 FPS sources, use `DETECTION_FRAME_STRIDE=2` (25 Hz sampling).

[Integration] Real 60-second clip, cached tracks, same tracks at 25 Hz and 5 Hz:

| Metric | Window 0 (25 Hz / 5 Hz) | Window 0.2 s (25 Hz / 5 Hz) |
| --- | --- | --- |
| Pooled speed | 2.90 / 2.40 m/s | 2.30 / 2.40 m/s |
| Same-track speed ratio (median, p90) | 1.21, 1.81 | 0.98, 1.36 |
| Per-track max speed median | 8.08 / 4.33 m/s | 4.43 / 4.33 m/s |
| Tracks with max ≥ 10 m/s | 36 / 1 | 0 / 1 |
| Time at ≥ 7 m/s | 5.20% / 1.15% | 0.61% / 1.15% |
| Active seconds | 643 / 644 | 608 / 644 |
| Movement rows stored | 14,603 / 2,945 | 2,702 / 2,945 |

Sprint count on this clip is 0 under both methods; no real sprint ground truth
exists.

## 9. Heatmaps and team tactics

[Math] Existing hand-verifiable tests cover cell assignment, time weighting,
boundary cells, occupancy fractions, centroid, width/depth, compactness,
pairwise spacing, hull degeneracy, insufficient snapshots, Unknown exclusion and
centroid separation; a new test pins windowed heatmap time to each window's start
cell. [Integration] The end-to-end run on this branch regenerated every heatmap
and, with the original team labels, the team tactics and series identically to
the saved results. Heatmap time follows the movement windows (same cells,
coarser 0.2 s steps). The UI centroid path no longer bridges unobserved frames.

## 10. Processing performance

Measured, not assumed: detection 10.5 frames/s at 640 on 1920 × 1080 (7.6 at 960,
5.2 at 1280); ByteTrack replay about 0.3 s per 150 frames; team sampling about
1 s per clip from JPEG frames. The speed window cuts stored movement rows by 81%
at 25 Hz (14,603 → 2,702), shrinking analytics bundles and their reads. Analytics
API requests check artifacts by size and modification time (no hashing); no page
view triggers processing. No further optimisation was justified by measurement.

## 11. Job dependencies and stale outputs

Unchanged and verified: each job records exact upstream job, attempt and
calibration versions; readers return 409 when anything changed; team-label
changes invalidate tactics and reports but not detection, tracking or player
analytics; nothing reprocesses automatically. After upgrading, results saved
earlier stay readable and current under their recorded method
(`consecutive_clean_intervals_v1`, speed window 0, shown as such in the UI);
rerun player analytics (and then the report) to apply the 0.2 s window, and rerun
classification for seeded matches to apply the vote rule.

## 12. API, PDF and CSV consistency

All three read the same saved bundles; nothing is recalculated on read. The
speed window is recorded in the summary, exposed on player rows
(`speed_window_seconds`) and printed in the PDF methodology. Units, nulls and
team identities are unchanged. The single deliberate difference is presentation
of unmeasured movement (API/CSV numeric 0 with zero active time; UI/PDF
"Unavailable"/"—").

## 13. Regression tests

All executed on the final branch code unless stated.

| Check | Result |
| --- | --- |
| Backend pytest (full) | 1,232 passed in 733 s (1,215 before this branch; 17 new) |
| Ruff check / format, Alembic | Passed / 237 files formatted / single head `0015_team_color_prototypes` |
| Frontend Vitest (full) | 245/245 in two consecutive runs (243 before this branch, +2 new). One earlier run had one failure while the machine was heavily loaded (test environment set-up 268 s instead of 22 s); the test passed alone (1.2 s) and in both following full runs. No timeout was changed. |
| ESLint, TypeScript, production build | Passed; Analytics chunk 449 kB (131 kB gzip), no chunk over 500 kB |
| Browser sweep (Playwright/Edge, isolated QA API) | 178/178 checks, 81 screenshots, at 390/834/1440/1920 px and 844 × 390 |
| End-to-end CV run (isolated copy, real Redis/RQ workers, CPU YOLO) | All 9 jobs completed; detection, tracking, coordinates, trajectories and all 19 tracks' analytics and heatmaps identical to the saved results; after re-applying the original manual team labels, team tactics, both series and both CSVs identical; the 8-page PDF differs only in its timestamp, job IDs, the new methodology sentence and dashes for the four tracks without a measured movement window. The script's own heatmap probe samples a motionless track and reports "no cells" for it, as in Stage 9. |

New tests: speed window (jitter, remainder extension, short runs, rejected
observations, sprint duration, streaming bounds, heatmap start cell, settings,
worker summary), seeded votes (typical crops accepted; ambiguous, distant and
incoherent crops abstain; confidence share), detection evaluator (tracking
candidates excluded), PDF (unmeasured movement as dashes, speed window stated),
frontend (speed basis text, unmeasured movement, centroid path gaps).

## 14. Unresolved limitations

- Tracking fragmentation (median span under 1 s on the fixed-camera clip) limits
  per-track KPIs and team coverage; no safe stitching exists.
- Coordinates are metre-level approximations (held-out errors 0.9–4.4 m on the
  panorama); no surveyed ground truth exists for distance or speed.
- Full-cadence cleaning splits tracks at bounding-box jumps (1,183 vs 232
  segments at 25 vs 5 Hz), which the speed window turns into unmeasured short
  runs; a pixel-scale-aware plausibility tolerance is a candidate improvement
  that needs its own validation.
- Automatic team classification remains conservative (8% coverage); seeded mode
  is the practical path and can still label a dark-kitted referee.
- Ground truth is small: three distinct six-second broadcast clips (plus two
  same-game confirmation clips). Results do not establish broad accuracy.
- Phases 16–17 (ball, possession, passes, shots) remain deferred.

## 15. FYP evaluation readiness

Defensible today: the KPI definitions and formulas (catalogue), the noise analysis
and the 0.2 s window (synthetic truth plus cadence agreement), the GT-scored
detection, tracking and seeded team results, and the explicit rejection of
changes that did not generalise. Present coordinates and speeds as approximate,
use seeded team colours rather than automatic labels, and show the held-out
landmark table when asked about metre accuracy. For new matches, prefer fixed
cameras, calibrate with eight or more markings, and expect Unknown labels for
short tracks.

## Reproduction

From the repository root in the WSL environment; every output folder must be new.

```bash
python scripts/evaluate_movement_kpis.py --tracks storage/evaluation/post-phase18/continuity-60s/baseline-tracks-stride1.csv \
  --database storage/footlytics.db --match-id 1 --strides 1 5 --speed-windows 0 0.12 0.2 0.32 0.4 --output <new>
python scripts/evaluate_speed_window.py --output <new>
python scripts/evaluate_team_classification.py --dataset data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --predictions storage/evaluation_inputs/kpi-quality-baseline-v1/predictions.json --frames-root data/external/soccernet_gsr/raw \
  --mapping-root data/external/soccernet_gsr/converted/distinct-games-v1 [--seed-examples 3] --output <new>
python scripts/evaluate_detection_settings.py --dataset data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --image-sizes 640 960 1280 --output <new>
python scripts/evaluate_tracking_settings.py --dataset data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --predictions storage/evaluation_inputs/kpi-quality-baseline-v1/predictions.json [--set track_high_thresh=0.35] --output <new>
python scripts/evaluate_calibration_landmarks.py score --database storage/footlytics.db --match-id 1 \
  --located docs/kpi-landmarks-60s.json --output <new>.json
python scripts/evaluate_continuity.py --detections storage/evaluation/post-phase18/continuity-60s/detections-full.csv \
  --summary storage/evaluation/post-phase18/continuity-60s/detection-summary-stride1.json \
  --video storage/raw/matches/1/757559cc56df4d43be4a07ba11068826.mp4 --team-colors docs/hardening-seed-prototypes.json \
  --seconds 60 --strides 5 1 --output <new>
```

The database is only ever copied before reading. Retained evidence (git-ignored)
is under `storage/evaluation/kpi-quality/`: `movement-windows-60s`,
`speed-window-synthetic-v1`, `soccernet-baseline-v1-reported`, `teams/`,
`detection-imgsz`, `tracking/`, `landmarks-60s`, `continuity-60s-seeded-v2`
(with `contact-sheet-stride1.png`). Current-code SoccerNet predictions are in
`storage/evaluation_inputs/kpi-quality-baseline-v1/`. Phase 15 and hardening
results were not modified.
