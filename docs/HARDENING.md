# Post-Phase-18 hardening record

**Status: implementation and documentation finalized (8 October 2026).**
Targeted post-fix verification passed. The complete backend suite was **not**
rerun after the migration fix; no clean post-fix full-suite pass is claimed.

Scope: signup, preparation deduplication, continuity evaluation, honest coverage,
user-seeded colors and presentation polish. Phases 16–17 remain OPTIONAL / DEFERRED.
Frozen Phase 15 SoccerNet results, settings and datasets were not modified or rerun.

## Access and preparation

Signup requires exactly one of Coach, Analyst, Player or Club Management. Admin
injection, missing roles, role substitution and multi-role approval are rejected.
Older requests keep a nullable role and need an explicit non-admin choice. Pending
or rejected requests cannot sign in; approved accounts receive the requested role.
Passwords use the existing hash service and are cleared from requests after review.

The current video preparation endpoint is independent of history pagination.
Queued/running duplicates return 409; successful current preparation is reused
with 202 and no enqueue. Failed attempts remain retryable; replacing the source
allows new preparation. Older jobs remain in collapsible Processing History.

Migrations `0014_signup_requested_role` and `0015_team_color_prototypes` were
rehearsed on a populated copy, then applied after a fresh development backup.
All values in every pre-existing column were compared before/after and preserved:
2 users, 2 clubs, 4 teams, 2 matches, 1 video, 1 calibration, 12 jobs, 787 assignments
and 1 signup request (plus role/membership tables). Unique head/current is
`0015_team_color_prototypes`; `alembic check` found no new upgrade operations.

The running API had still been the pre-role version and rejected `requested_role`.
Restarting the migrated API/worker fixed signup; the live endpoint returned 202,
and isolated browser verification proved new-request creation through approval.
No QA login accounts were added to the development database.

## Controlled continuity comparison

Source: first **60.0 seconds / 1,500 frames**, 25 FPS, 4096 × 734, of the existing
five-minute SoccerTrack clip. YOLO11n, CPU, four threads, image size 2560,
confidence 0.25, unchanged ROI. One previously completed full-cadence inference
pass supplied both comparisons; this continuation did **not** rerun YOLO.

| Metric | Sampled every 5 frames | Every frame | After offline stitching |
| --- | ---: | ---: | ---: |
| Original / canonical track count | 181 / 181 | 251 / 251 | 251 / 251 |
| Tracks with ≥2 observations | 164 | 236 | 236 |
| Tracks with a consecutive sampled interval | 160 | 235 | 235 |
| Mean span, s | 2.5691 | 2.7476 | 2.7476 |
| Median span, s | 1.60 | 0.96 | 0.96 |
| P90 / P95 span, s | 7.00 / 8.40 | 7.92 / 12.04 | 7.92 / 12.04 |
| Longest span, s | 17.00 | 39.64 | 39.64 |
| Tracks <2 s | 102 | 168 | 168 |
| Tracks ≥10 / ≥30 s | 5 / 0 | 17 / 1 | 17 / 1 |
| Total consecutively observed track-seconds | 303.00 | 610.32 | 610.32 |

Span is last minus first timestamp and may contain gaps. Total observed
track-seconds sums only consecutive sampled intervals across all tracks; it is
**not** cleaned physical heatmap occupancy, and can exceed clip length because
several people are visible at once. IDs/minute (181 versus 251) is only a
fragmentation proxy. Without matched ground truth it is not IDF1 or identity
accuracy. Longer maximum tracks plus more short fragments do not establish
an overall continuity improvement.

The existing detector default was already `DETECTION_FRAME_STRIDE=1`. The original
five-minute helper explicitly used stride 5 for performance. ByteTrack receives
one update per sampled frame, including empty frames. Installed Ultralytics
8.4.170 has no frame-rate constructor parameter; `TRACK_BUFFER=30` counts updates:
6 seconds at 5 Hz, 1.2 seconds at 25 Hz. High/low/match thresholds remain
0.25/0.10/0.80. Detector confidence 0.25 means its saved CSV supplies no lower-score
boxes to the tracker's second stage. No unmeasured threshold relaxation was adopted.

The original full-cadence pass took **462.1955 s total**, with **436.1498 s inference**
(3.4392 inference FPS). The stride-5 subset's summed inference times were
91.8401 s / 3.2665 inference FPS; that is a subset of the same pass, not a separately
measured wall-clock run. Final cached tracking replay took 3.2327 s at stride 5
and 2.3167 s at stride 1; these include replay setup, not detection. Do not compare
these numbers to the historical 300-second run as if durations were the same.

## Stitching decision: rejected for production

The offline evaluator requires non-overlap, gap ≤0.6 s, speed ≤10 m/s,
three motion observations at both ends, bidirectional motion residual ≤0.75 m,
bbox scale ratio ≤1.25, reliable existing appearance and CIE Lab distance ≤8.
It rejects ambiguous candidates and an observed competitor within 2 m near either
boundary (±0.08 s), and prevents chained temporal overlap. Pitch motion relies on
the existing approximate calibration, not independently validated metre accuracy.

**Zero merges were accepted.** Rejections: temporal overlap 3,114; excessive gap
27,617; impossible speed 467; insufficient motion 200; scale mismatch 40;
insufficient appearance 7; inconsistent motion 14; impossible motion 9.
Only four tracklets had eligible aggregate appearance. Safety tests cover valid
continuation, overlaps, speed, gaps, ambiguity, crossing players, scale and chains.

Original/canonical IDs and source/destination/gap/reasons are retained in the
experimental CSVs. Production ByteTrack, track IDs and heatmap grouping are
unchanged. No occupancy is created over gaps; no canonical ID is claimed to be a
real player. There is no demonstrated safe continuity improvement on this clip.

## Classification and user-seeded colors

The user specified **Team A = blue; Team B = white**. Three visually reviewed real
examples per team were selected, without benchmark annotations. Prototypes and
sample references are recorded in [hardening-seed-prototypes.json](hardening-seed-prototypes.json).
The experiment uses raw OpenCV crops; production previews use the protected frame
endpoint's JPEG round trip, so it is not an exact production-crop equality claim.
Seed examples come from the same clip; these are coverage results, not held-out
accuracy or automatic club recognition.

| Cadence / mode | Team A | Team B | Unknown | Classified coverage | Unknown % |
| --- | ---: | ---: | ---: | ---: | ---: |
| Stride 5 automatic, before | 0 | 1 | 180 | 0.55% | 99.45% |
| Stride 5 user-seeded, after | 0 | 1 | 180 | 0.55% | 99.45% |
| Stride 1 automatic, before | 1 | 0 | 250 | 0.40% | 99.60% |
| Stride 1 user-seeded, after | 0 | 3 | 248 | 1.20% | 98.80% |

The automatic A/B order comes from cluster ordering, not user-labelled kit identity.
At stride 1 the final sampler produced 597 feature-bearing torso crops from
1,288 candidates: 618 tiny/outside crops rejected, 73 valid candidates skipped by
the bounded sample budget, zero feature-conversion rejections. It decoded 434
selected frames. Median samples per track: 1; median sample quality: 0.6395.
All 248 Unknown seeded tracks lacked enough consistent samples. No blue track met
the unchanged minimum of three confident observations. At stride 5 there were
437 feature-bearing crops, 268 tiny/outside rejects and 180 insufficient tracks.
Prototype separation was 62.2530 CIE Lab units. Feature-bearing does not imply
sufficiently reliable evidence for a team label.

Sampling now spreads the existing bounded budget across each track's lifetime;
tiny invalid crops do not consume valid sample slots. The seeded classifier uses
both prototypes, the existing 0.6 threshold, at least three actual agreeing
samples, robust median/consistency aggregation, and rejects any confident
opposite-team evidence. No samples are duplicated. A dominant-color candidate and
other unsuccessful variants were rejected and retained only as local experiments.

The practical UI is **Team Assignments → Set Team Colors**: preview current
track/frame crops, add examples to both teams, save, then queue reclassification.
Up to ten samples are accepted; same-crop duplication and assigning one track to
both teams are rejected. The backend measures colors itself, rechecks access and
tracking after frame decoding, and preserves versioned prototype history. Jobs
snapshot/recheck the prototype set and source versions; changed inputs fail safely.

Assignment provenance records automatic/user-seeded mode, prototype/sample IDs,
sample count, accepted/rejected evidence, confidence/margin and Unknown reason.
Manual overrides remain highest priority. Saving prototypes does not overwrite
existing assignments; successful classification publishes them. Effective team
changes require corresponding team tactics/reports to be regenerated. Club
Management is read-only; Player cannot change colors or run processing.

## Heatmaps and presentation

Player details and heatmaps show observed seconds / source-video seconds and
backend-computed coverage. Under 15 observed seconds is a short fragment; otherwise
under 20% is low coverage. These are display cautions, not accuracy claims.
Unknown/inconsistent video duration yields unavailable coverage. Existing cleaned,
time-weighted bins and pitch axes (X length / Y width) remain unchanged. Active
duration can sort the current player page; short fragments remain accessible.

The [layered architecture](architecture.svg) separates UI, API/auth/services,
SQLAlchemy/database, Redis/RQ, worker and protected storage/results. The separate
[CV pipeline](cv-pipeline.svg) shows data dependencies, seeded colors and the
rejected offline stitching experiment. Both are vector SVGs with inspected A4
exports. UI status badges, compact history, metric cards, responsive forms and
scrolling tables use the existing design; frontend KPIs are not recomputed.

## Reproduction without inference

Use the existing WSL environment. The output directory must be new; old evidence
is never overwritten. The paths below are local retained artifacts, not a new
dataset/model download. Source SHA-256 and artifact hashes are in
[hardening-results.json](hardening-results.json).

```bash
cd "/mnt/d/VS Projects/FYP_Footlytics"
source "$HOME/.venvs/footlytics-yolo/bin/activate"
python scripts/evaluate_continuity.py \
  --detections storage/evaluation/post-phase18/continuity-60s/detections-full.csv \
  --summary storage/evaluation/post-phase18/continuity-60s/detection-summary-stride1.json \
  --video storage/raw/matches/1/757559cc56df4d43be4a07ba11068826.mp4 \
  --team-colors docs/hardening-seed-prototypes.json \
  --seconds 60 --strides 5 1 \
  --output storage/evaluation/post-phase18/continuity-60s/reproduction-seeded
```

Omit `--team-colors` and choose another new output directory for automatic mode.
The CLI streams cached CSVs and selected real video frames; it never calls YOLO or
writes the application database. Stitch safety tests can be reproduced with
`python -m pytest backend/tests/test_tracklet_stitching.py -q`; the measured
experiment is retained as `stitching-evaluation.json`, `stitch-decisions.csv` and
`stitched-experiment.csv` under the artifact root above.

## Final verification

| Verification | Exact recorded result |
| --- | --- |
| Initial complete backend regression | **1,177 passed, 7 failed, 0 errors, 0 skips**, **755.47 s**, **4 warnings** |
| Post-fix coordinate + report suites | **92 passed**, manually verified and confirmed by the user |
| Remaining affected migration tests after the fix | **3 passed**, manually verified and confirmed by the user |
| Alembic current | `0015_team_color_prototypes (head)` |
| Alembic check | Passed; no new upgrade operations detected |
| SQLite integrity | `PRAGMA foreign_key_check` returned `[]` |
| Ruff / formatting | Passed; **228 files already formatted** |
| Complete frontend suite | **175 passed**, no failures, **23.73 s** |
| ESLint / strict TypeScript / production build | Passed |
| Browser verification | **77 checks passed**, zero page errors |
| Architecture / CV pipeline diagrams | Rendered and visually inspected; each A4 export has one page |

The full backend suite ran once. All seven initial failures shared the migration
0015 SQLite downgrade/foreign-key cause documented below. The post-fix evidence
is targeted testing, **not a rerun of the complete backend suite**. Do not add the
92 and 3 to the initial count or report a clean post-fix full-suite pass. Those two
manual results were supplied by the user on 8 October 2026; retained initial-run
counts/timing/warnings are in `.tools/hardening/full-backend-result.json` and its
JUnit/log files. The four warnings concern pytest `record_property` with JUnit
`xunit2` in player-analytics, report, team-analytics and trajectory tests.

Earlier focused classification verification recorded **117 passed in 84.62 s**.
Signup/preparation/coverage checks and stitching safety tests are retained in
`.tools/hardening/`. Recorded FastAPI health returned `ok`, Redis returned `PONG`,
and the restarted API exposed all four non-admin signup roles and color routes.
This final continuation changed documentation only; it did not repeat automated
suites, YOLO, Phase 15, tracking experiments or team-color experiments.

Browser: **77 checks passed, zero page errors**, production build and real API
without HTTP interception, at 1440 × 1000, 390 × 844 and 320 × 844. No page-wide
overflow. Verified signup/pending denial/exact-role approval/login/RBAC/logout,
primary domain pages, prepared-job reuse/history, calibration, detection/tracking
JPEGs, metrics, heatmap, team tactics, assignments, six real crop examples,
prototype persistence, queued classification, PDF and both CSV downloads.
The browser queue was recording-only: classification was submitted, not executed
on the five-minute video. Worker behavior is covered by focused integration tests;
real classification on the controlled 60-second clip was executed by cached replay.

Current development results were made stale by the old duplicate preparation jobs
changing `video.updated_at` after results were published. This was detected in
browser QA, not bypassed. Report/heatmap checks then used an isolated migrated copy
of the preserved pre-duplication backup, with read-only hardlinks to real artifacts.
The live database was not restored or overwritten; old jobs/results remain intact.
Regenerating classification and coordinate/downstream results against current
saved tracks is a separate action; it does not require new YOLO inference.

## Migration 0015 fix and rationale

SQLite batch column removal rebuilds a table. During the original downgrade,
`processing_jobs` was rebuilt while `track_team_assignments` still had its incoming
composite foreign key; dropping the parent table therefore failed. Empty-database
round trips had passed, while the populated legacy migration tests exposed this.

The existing fix in `0015_team_color_prototypes.py` now:

1. Refuses downgrade when prototype history (including retired sets) or a saved
   team-color job snapshot exists, so that evidence is not silently discarded.
2. Removes the empty new prototype table before rebuilding its referenced parent.
3. Temporarily detaches the assignment composite foreign key for SQLite, removes
   the new columns, then restores the same `(match_id, tracking_job_id)` reference
   to `processing_jobs(match_id, id)` with `ON DELETE RESTRICT`.

This preserves assignments/manual overrides and restores enforcement rather than
turning off SQLite foreign-key checks globally. The legacy coordinate migration
test compares all historical-schema columns, then verifies the entire assignment
row again after upgrading to head, including the new default provenance columns.
Older migrations were not rewritten. Downgrade testing used disposable databases;
the development database remains at head, with valid foreign keys. This final
continuation only documents that already-verified fix.

## Remaining limitations

- Tracking remains fragmented. More long spans at full cadence came with more
  short tracks; an overall identity-continuity improvement has not been shown.
- No safe tracklet stitch was accepted, so production does not merge fragments.
- User-seeded classification remains sparse on cached data: **3/251 classified**
  at full cadence, **248/251 Unknown**. No blue track met the evidence minimum.
  Unknown labels are retained instead of forcing an assignment; coverage is not
  accuracy, and the seed examples are not an independent validation set.
- Homography assumes a static camera and planar pitch. Camera motion or zoom can
  invalidate calibration; independent coordinate accuracy remains unverified.
- Heatmaps cover usable observed intervals only, not a player's complete match.
- The current five-minute development outputs described above are stale. This
  documentation pass did not regenerate them or bypass their freshness guards.
- Post-fix backend evidence is targeted verification; the full backend suite was
  not rerun after the correction.

Local QA credentials, databases, logs, media, model weights and builds remain in
ignored runtime locations. This folder has no Git metadata or Git executable, so
no commit-history secret audit is claimed. Frozen Phase 15 sections were checked
unchanged during documentation edits. Classification and tracking limitations
above remain substantial; this hardening is not a claim of robust full-match
identity tracking or automatic team accuracy.
