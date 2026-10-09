# FOOTLYTICS implementation plan

Phases 1–15 are complete; the dashboard, PDF reports and CSV exports present saved analytics.
**Phase 5 — COMPLETE. Phase 6 — COMPLETE. Phase 7 — COMPLETE. Phase 8 — COMPLETE. Phase 9 — COMPLETE. Phase 10 — COMPLETE. Phase 11 — COMPLETE. Phase 12 — COMPLETE. Phase 13 — COMPLETE. Phase 14 — COMPLETE.**
**Phase 15 — COMPLETE. Phases 16 and 17 — OPTIONAL / DEFERRED. Phase 18 — COMPLETE.**
Phase 15 includes real evaluation on three SoccerNet source games. The final core
scope is Phases 1–15 plus Phase 18 integration and release verification. Ball and
ball-event features are intentionally deferred, not failed.
Complete each phase's acceptance checks before treating
its outputs as available. Keep changes small enough to explain during the viva.

## Architectural constraints

- Recorded post-match video; 11v11 and 5v5; CPU operation remains supported.
- Browser → REST API → Redis/RQ → Python worker for long-running processing.
  Jobs return IDs promptly, expose progress, and persist useful failure details.
- SQLAlchemy models and Alembic migrations; SQLite first, PostgreSQL-compatible
  types/relationships where possible. No schema creation during API startup.
- Entities introduced through Phase 5A: User, Role, Club, ClubMembership, Team,
  Player, SquadMembership, Match, MatchVideo, ProcessingJob and PitchCalibration.
  Phase 8 adds TrackTeamAssignment. Planned later entities: Track,
  PlayerAnalytics, TeamAnalytics, MatchEvent, Report and AuditLog. Introduce each
  when needed, rather than creating the entire schema in Phase 2.
- Roles: Admin (administration), Coach (matches and analytics), Analyst
  (processing/analysis), Player (permitted individual analytics), Club Management
  (summaries, team analytics, reports). Phase 2 enforces account administration and
  own-profile access. Phase 3 supplements role capabilities with SQL club scopes;
  future resources must reuse them. Roles alone do not establish club ownership.
- Pitch X = length, Y = width, in metres. Match records store their own
  `pitch_length_metres` and `pitch_width_metres` for either match format.
- Map the bottom-centre of each player box: `((x1 + x2) / 2, y2)`.
- Use pretrained detection and ByteTrack behind a replaceable interface. A track
  ID is match-local, not a human identity. No face recognition or biometric links.
- Never substitute invented numbers for missing or unreliable observations.
  Show Unavailable/empty states and explain coverage and uncertainty.
- Ball/event inference is optional. No manual football-event annotation, arbitrary
  xG formulas, or custom model-training pipeline. Offline evaluation annotations
  are small ground-truth fixtures, not a product annotation feature.

## Phase 1 — Project bootstrap

**Status: complete.** Its working structure and health endpoint are retained.

- **Objective:** Establish a runnable, understandable foundation without domain
  features or CV algorithms.
- **Major modules:** React entry, router, providers, empty-state page; FastAPI
  application, health route/schema, core settings; placeholder packages, storage,
  tests and documentation.
- **Dependencies:** Python/Node tooling; minimal web/database/queue dependencies.
  Redis runtime and CV libraries are unnecessary for bootstrap checks.
- **Main outputs:** Directory layout, dependency manifests/locks, environment
  example, Git exclusions, README, persistent rules and this plan. Optional Redis
  Compose service; no worker, migrations, auth or processing implementations.
- **Important tests:** Frontend type check/build/lint and shell navigation; API
  import and health contract; settings validation/environment precedence/path
  stability; CORS allowlist; structure and HTTP startup smoke checks.

## Phase 2 — Database, authentication and RBAC

**Status: complete — verified 2026-09-29.**

- **Objective:** Establish persistence and enforce authenticated resource access.
- **Major modules:** `database`, `models`, `schemas`, `auth`, `services`, `api`,
  Alembic; frontend auth feature, login page and session-aware API access.
- **Dependencies:** Phase 1; PyJWT, pwdlib/Argon2id, email-validator and the role
  permission matrix documented in README.md.
- **Main outputs:** Engine/session/base, reviewed initial migration for users,
  roles and user_roles only; role seeding and first-admin CLI; password hashes,
  JSON login, expiring bearer JWTs, current-user route and reusable backend role
  dependencies. Admin CRUD supports activation and multiple roles. The frontend
  provides login, protected shell, role guards and user management, with centralized
  tab-scoped token storage and browser-side logout. Startup requires a strong
  configured secret. No default accounts/passwords or club entities are supplied.
- **Important tests:** SQLite migration upgrade/downgrade on temporary databases;
  password verification, token expiry/tampering, invalid credentials, disabled
  users, forbidden admin access, response secrecy and frontend unauthorized states.
  Schema types are portable; a live PostgreSQL run remains deferred.
- **Verification:** 64 backend tests; 17 frontend tests; Ruff, ESLint, TypeScript
  and production build passed. Alembic upgrade/current/check passed against the
  development database; isolated tests cover downgrade/re-upgrade. A live headless
  Edge run with a separate SQLite database verified first-admin creation, login,
  Coach creation, role/status edits, Coach login and session restoration, frontend
  denial, backend 403, logout and anonymous 401. No browser runtime errors occurred.

## Phase 3 — Clubs, teams, players and match management

**Status: complete — verified 2026-09-29.**

- **Objective:** Manage football entities and match metadata within authorized scope.
- **Major modules:** Entity models/migrations, schemas, services, routes; frontend
  teams, players and matches features/pages.
- **Dependencies:** Phase 2 identities, permissions and database infrastructure.
- **Main outputs:** Club/team/player records and memberships; matches supporting
  11v11/5v5, teams, date and per-match pitch dimensions; list/detail/create/edit
  screens and validated relationships. Human player records remain distinct from
  observed track IDs.
- **Important tests:** CRUD validation and ownership; cross-club isolation;
  positive/plausible pitch dimensions; membership changes; foreign keys and
  delete policies; empty and failed UI states.
- **Implementation:** Six new tables in revision `0002_clubs_teams_players_matches`;
  scoped services/routes, optional unique User↔Player links, composite same-club
  foreign keys, active squad uniqueness, immutable ownership, soft removal and
  archive/restore. Frontend club/member, team/squad, player and match management
  reuses the existing auth provider/client and TanStack Query. Home counts come
  from scoped APIs; video/analytics remains explicitly unavailable.
- **Verification:** 109 backend regression/domain/migration tests and 33 frontend
  regression/domain tests passed, along with Ruff lint/format, ESLint, TypeScript/build, Alembic
  upgrade/current/check, startup and structure checks. A separate SQLite/Edge
  workflow covers Admin club assignment, Coach teams/players/squad/match creation,
  cross-club denial and Club Management read-only access. No production fixtures.
- **Limitations:** SQLite verified; live PostgreSQL deferred. Player reads follow
  current active memberships, not historical match lineups. Club-specific roles,
  cross-club transfers and CV identity matching are not implemented.

## Phase 4 — Video upload, validation, storage and background jobs (complete)

- **Objective:** Safely accept recorded footage and establish asynchronous jobs.
- **Major modules:** Video/job models and migrations, storage/video/job services,
  API upload/status routes, `workers`, frontend upload/processing features.
- **Dependencies:** Phases 2–3; Redis/RQ; FFmpeg/ffprobe or validated metadata reader;
  multipart support and worker process environment.
- **Main outputs:** Authorized uploads with generated safe filenames and bounded
  size; footage metadata in DB, files in `storage/raw`; validation failures;
  ProcessingJob lifecycle, enqueue/worker/status contract, frontend polling.
  Specify queue/database consistency, duplicate-job handling, retry/cleanup and
  cancellation policy before processing is added.
- **Important tests:** Oversize/truncated/unsupported files, path traversal,
  spoofed extension, disk failure, unauthorized access; unavailable Redis, enqueue
  failure and worker failure; job transitions/idempotency; immediate API return.
  Use tiny valid and invalid clips, never full matches.
- **Implementation:** Revision `0003_match_videos_processing_jobs` adds MatchVideo
  and ProcessingJob, with one active source, same-match job/video foreign keys,
  controlled statuses/types, bounded progress and active-job uniqueness. Bounded
  multipart upload, SHA-256, generated relative paths, atomic finalization and
  explicit replacement reuse the existing match/club permissions. Failed uploads
  clean up; retired sources remain history. A shared short match-row transaction
  serializes replacements and job mutations and rechecks access after inspection.
  ffprobe metadata and real frame decoding are bounded subprocesses; missing
  ffprobe uses an explicitly warned OpenCV fallback. No calibration/CV analytics.
- **Background contract:** API persists a queued record before submitting job ID
  and attempt to JSON-serialized RQ. Separate Linux/WSL worker sessions reopen the
  source, check size/readability, refresh metadata and record milestones. Failed
  submissions return 503 and persist failure without a synchronous fallback.
  Retry resets transient fields with a new attempt/RQ ID; stale and duplicate
  deliveries cannot claim work. Active jobs block source replacement. Frontend
  upload, replacement, actual metadata and role-aware preparation/retry/polling
  are integrated into match details. Active jobs stay first when browsing history.
- **Verification:** 220 backend and 51 frontend tests passed, retaining all
  Phase 1–3 coverage. Ruff lint/format, ESLint, TypeScript/build, Alembic
  upgrade/current/check, FastAPI startup/OpenAPI and structure checks passed.
  Isolated Edge desktop/mobile checks passed for real MP4/MOV upload/replacement,
  invalid-file cleanup, safe history, protected ranges and role/club denial.
  A real Redis connection failure produced a visible persisted failed job.
- **Environment and limitations:** ffprobe, Redis and Docker were unavailable;
  real fallback decoding passed and probe behavior uses test doubles. Live RQ
  delivery was not tested; queue injection and the real worker function verified
  successful processing, progress, failures and retry safety. Worker startup
  requires Linux/WSL. No cancellation, automatic retention/crash reconciliation,
  client upload resumption, full-match decode scan or browser player. Abrupt
  filesystem/DB/queue boundary crashes need maintenance reconciliation. PostgreSQL
  remains unverified. Ready for Phase 5 only when instructed.

## Phase 5 — Pitch calibration and homography

**Phase 5A — Backend calibration/homography complete.**
**Phase 5B — Calibration frontend complete. Phase 5 — complete.**

- **Objective:** Define and validate the camera-to-pitch transformation.
- **Major modules:** PitchCalibration model/service/schemas/API;
  `cv/homography.py`; frontend calibration feature.
- **Dependencies:** Match dimensions, validated footage/frame extraction from
  Phases 3–4; existing OpenCV and NumPy dependencies.
- **Main outputs:** Landmark selection with at least four point correspondences,
  `cv2.findHomography()` result and calibration metadata in PitchCalibration JSON
  fields; protected JPEG frame extraction and the calibration frontend.
  State coordinate origin/orientation and frame resolution explicitly. Reject
  degenerate geometry and provide reprojection feedback. Establish fixed-camera
  validity; camera pan/zoom/cuts require recalibration or invalid-segment flags.
- **Important tests:** Known transforms with explicit synthetic fixtures,
  collinear/duplicate/mismatched points, dimensions/axis conventions, reprojection
  error, save/reload and access control; no transformation from invalid calibration.
- **Phase 5A verification:** 64 focused calibration/homography/migration tests and
  279 full backend tests passed; the full suite ran once. Ruff lint/format,
  Alembic upgrade/current/check and FastAPI import/startup passed. Migration
  `0004_pitch_calibration` preserves earlier data. Calibrations are tied to the
  active video and pitch dimensions; replaced or stale mappings are not current.
- **Phase 5B frontend:** Match Details links to `/matches/:matchId/calibration`
  when a video exists. Authenticated timestamp-selected frames, original-pixel
  coordinates and an SVG pitch using Match metres support 4–64 numbered pairs,
  remove/reset, explicit create/update and backend reprojection feedback.
  Changing frames clears draft points; saved quality is labelled separately.
  Admin/Coach/Analyst editing and read-only views reuse existing capabilities.
  Interior markings are schematic; camera movement still requires recalibration.
- **Phase 5B verification:** 23 focused calibration tests and 74 full frontend
  tests passed; the full suite ran once. ESLint, TypeScript and production build
  passed. Backend/migrations were unchanged, so backend and browser workflows
  were not rerun. Ready for Phase 6A when requested; no detection or analytics added.

## Phase 6 — YOLO player detection

**Phase 6 — COMPLETE (detection backend, verified CPU inference and result review).**

- **Objective:** Detect players using a pretrained model without custom training.
- **Major modules:** `cv/detector.py`, pipeline stage and worker integration.
- **Dependencies:** Phase 4 worker/video access; Ultralytics, configured pretrained
  weights and CPU runtime. Document model source, version and license.
- **Main outputs:** Typed timestamped detections with boxes/classes/confidences;
  configurable confidence/device; CPU path and optional CUDA selection. Person
  detections are not automatically proven players; record filtering assumptions.
- **Important tests:** Box/confidence format, empty detections, model-load errors,
  frame timing and coordinate scale; small opt-in CPU clip smoke check. Default
  tests use explicit fixtures or detector doubles without weight downloads.
- **Phase 6A outputs:** Settings-driven `yolo11n.pt` adapter, incremental frame
  decoding, conservative four-corner ROI filtering and protected CSV artifacts in
  image coordinates. Existing scoped jobs/RQ now support `player_detection`,
  source/calibration validation, safe failures and retries; migration
  `0005_player_detection` preserves preparation history. No tracking, coordinate
  mapping, detection UI or analytics were added.
- **Phase 6A verification:** 56 focused tests and 335 full backend tests passed;
  the full suite ran once. Ruff lint/format, FastAPI startup and Alembic
  upgrade/current/check passed, with `0005_player_detection` at head and no drift.
  The one-image real smoke attempt could not reach inference because Windows
  PyTorch failed to initialize `c10.dll` (`WinError 1114`), including outside the
  sandbox. A later WSL2 CPU smoke test passed using the existing detector;
  CUDA and live Redis/RQ delivery remain unverified.

- **Detection review:** Protected current-result summary and JPEG preview endpoints
  read existing CSVs without inference. Match Details opens a review page with
  counts, job state, confidence-labelled boxes and processed-frame selection.
  Existing job APIs provide scoped start actions; Club Management is read-only,
  Player/anonymous/cross-club access is denied. Missing or stale results stay unavailable.

## Phase 7 — ByteTrack player tracking

**Phase 7 — COMPLETE (tracking backend, persistent IDs and result review).**

- **Objective:** Maintain player tracks within a match behind a replaceable API.
- **Major modules:** `cv/tracker.py`, tracking schemas/CSV, pipeline and worker.
- **Dependencies:** Phase 6 detections and true frame timing; a documented
  ByteTrack integration/version (prefer the existing detector ecosystem).
- **Main outputs:** BaseTracker contract and ByteTrack adapter; frame/timestamp,
  match-local track IDs and detection associations; artifacts in `storage/tracks`.
  Distinguish tracker IDs from player identities and document occlusion limits.
- **Important tests:** Stable IDs on short controlled sequences, empty frames,
  occlusions, ID switches, reset between matches and consistent frame skipping;
  substitute tracker contract tests.
- **Phase 7A outputs:** Real Ultralytics ByteTrack consumes existing detection CSVs
  without YOLO or video decoding. `player_tracking` jobs and the scoped POST route
  reuse ProcessingJob, JSON RQ delivery, retry ownership and current-input guards.
  Revision `0006_player_tracking` adds only provenance/summary metadata; image-space
  rows publish to protected attempt-specific CSVs after successful processing.
  Four centralized thresholds/buffer settings control association; empty sampled
  frames advance the tracker and real progress without fabricating observations.
- **Verification:** 61 focused tests and 396 full backend tests passed in WSL;
  the full suite ran once. Stable/multiple IDs, short gaps, invalid input, stale
  sources, artifact cleanup, retries and role/club isolation are covered using
  real ByteTrack. Ruff lint/format, FastAPI startup, dependency consistency and
  Alembic upgrade/current/check passed with `0006_player_tracking` at head.
- **Tracking review:** Protected summary/preview endpoints render saved boxes and
  IDs on one original frame without rerunning ByteTrack. The shared review page
  shows unique tracks, observation counts, average visible tracks and sampled-frame
  bounds. Current video, calibration, detection and tracking versions are checked
  before serving previews; no paths or full CSV rows are exposed through JSON.
- **Completion audit:** Phase 5 calibration requirements and existing tests were
  checked; calibration behavior was preserved. 24 focused backend review tests
  and 14 focused frontend tests passed. Full backend (420) and frontend (88) suites
  each passed in one run, along with Ruff, FastAPI startup, ESLint, TypeScript/build.
- **Limitations:** IDs are local to a match/attempt and may switch after occlusion;
  the buffer counts sampled frames. Earlier detection filtering limits recovery.
  Live Redis delivery and PostgreSQL remain unverified. Review uses bounded CSV
  scans and single-frame JPEGs; team classification follows in Phase 8 and pitch
  mapping in Phase 9. Movement analytics follow in Phase 11.

## Phase 8 — Team jersey classification

**Phase 8 — COMPLETE (backend).**

- **Objective:** Assign team labels from jersey evidence with human correction.
- **Major modules:** `cv/team_classifier.py`, streaming sample pipeline,
  assignment model/service/API and `team_classification` ProcessingJob worker.
- **Dependencies:** Existing Phase 7 CSVs, source-frame decoder, NumPy and OpenCV;
  no new dependencies or YOLO/ByteTrack reruns.
- **Outputs:** Clipped central torso crops, bounded multi-frame median Lab evidence,
  deterministic two-cluster K-Means, automatic Team A/B/Unknown and bounded quality.
  Ascending Lab centroids define A/B because configured kit colors are absent;
  human confirmation is required against actual teams. Scoped read/correction APIs
  preserve manual overrides on reruns and support explicit clearing.
- **Persistence and lifecycle:** Revision `0007_team_classification` adds track-level
  assignments and job provenance/summary fields. Source/calibration/detection/tracking
  guards, match locks and attempt ownership protect atomic publication. Old versions
  stay hidden; failed runs preserve earlier valid assignments and corrections.
- **Verification:** 96 focused Phase 8 tests plus 29 migration/review tests passed.
  Full backend regression passed 516 tests after updating the historical-schema
  downgrade test; its targeted rerun also passed. Ruff lint/format, FastAPI startup
  and Alembic upgrade/current/check passed; development records were preserved.
  A real four-frame synthetic-video smoke decoded three frames, aggregated six
  crops and persisted track 3 as Team B (0.996972), track 7 as Team A (1.0).
- **Limitations:** Color-only heuristic, no measured real-match accuracy or semantic
  referee/goalkeeper identification. Similar/striped kits, illumination and ID
  switches remain challenging. Live Redis/PostgreSQL are unverified. Frontend team
  correction remains unimplemented; frontend was unchanged.

## Phase 9 — Pitch coordinate conversion

**Status: COMPLETE (backend).**

- **Objective:** Convert tracked feet positions into match-specific metres.
- **Modules and inputs:** `cv/player_position.py`, bounded coordinate pipeline,
  shared tracking CSV reader, protected artifact/summary services and
  `coordinate_mapping` worker. Requires current Phase 7 tracks and Phase 5 saved
  calibration; independent of team assignments and without upstream CV reruns.
- **Geometry:** `((x1+x2)/2, y2)` approximates ground contact. Reuses Phase 5
  `transform_points()`/OpenCV; X is length, Y is width in Match-specific metres.
  Keeps off-pitch values unchanged and flags bounds with `1e-6` m tolerance.
  Invalid boxes are skipped/countable; corrupt metadata or numerical transforms
  fail safely. No trajectory cleaning or movement analytics.
- **Persistence and API:** Attempt-specific CSV retains track rows plus pixel/pitch
  points and `inside_pitch`. Revision `0008_coordinate_mapping` adds job metadata
  only. POST `/api/matches/{match_id}/jobs/coordinate-mapping` and protected GET
  `/api/matches/{match_id}/coordinates/summary` reuse role/club scope. Row-based
  progress, exact upstream snapshots, final revalidation and attempt ownership
  protect publication; failures retain previous valid results.
- **Verification:** 259 focused tests and 615 full backend tests passed; the full
  suite ran once. Phase 8/shared-reader and saved-result regression, populated
  0007-to-0008 record/override preservation, historical migrations, stale-input and
  retry safety passed. Ruff lint/format, FastAPI startup and Alembic
  upgrade/current/check passed; backed-up development records were preserved.
  Six-row smoke on a 30 × 20 m pitch gave `(15,40)` pixels → `(-2.5,20)` m outside,
  `(45,40)` → `(12.5,20)` m inside; two tracks, three inside and three outside rows.
- **Limitations:** Planar-pitch approximation; calibration/camera errors and
  occluded or inaccurate boxes propagate into raw positions. No camera-motion
  compensation or measured real-match accuracy. Live Redis/PostgreSQL remain
  unverified; frontend was unchanged.

## Phase 10 — Trajectory cleaning

**Status: COMPLETE (backend).**

- **Objective:** Produce defensible trajectories before deriving movement metrics.
- **Modules and input:** `cv/trajectory.py`, externally sorted coordinate reader,
  bounded pipeline, trajectory artifacts/summary API and existing ProcessingJob/RQ.
  Reads current Phase 9 output and its version chain without changing raw files,
  rerunning upstream CV or depending on team assignments. No new dependencies.
- **Cleaning:** Preserve every raw observation. Outside points and temporal
  conflicts have null clean positions. Neighbor consistency rejects isolated
  teleports while later points recover; persistent discontinuities and gaps over
  the configured limit start new per-track segments. Defaults are 12 m/s for the
  quality check and 2 seconds for continuity; these are configurable heuristics.
- **Smoothing:** Default three-observation window uses median residuals from a
  timestamp-linear baseline, moving halfway toward the estimate with a 0.5 m cap.
  Endpoints are preserved; rejected rows and segment breaks stop smoothing.
  **No interpolation:** missing observations remain gaps because cadence can vary.
- **Persistence and access:** Separate attempt-specific CSV retains bbox/pixel/raw
  positions alongside clean/null positions, segment, usability, status and source
  row provenance. Revision `0009_trajectory_cleaning` adds metadata only. Scoped
  POST `/api/matches/{match_id}/jobs/trajectory-cleaning` and GET
  `/api/matches/{match_id}/trajectories/summary` reuse existing authorization.
  Measured row progress, final version checks and atomic publication protect
  retries; previous valid results survive failure and team edits remain independent.
- **Verification:** 90 Phase 10 tests and 349 combined focused checks passed.
  Complete backend regression: 705 passed, 0 failed, 0 skipped; one full run.
  Populated 0008-to-0009 preservation, historical migrations, stale/retry/artifact
  guards, Ruff lint/format, FastAPI startup and Alembic current/check passed.
  Synthetic smoke: 12 source rows, 10 usable, one teleport and one outside rejection,
  two tracks, three segments, two smoothed rows and zero interpolation. Normal-sample
  jitter RMSE fell from 0.2000 m to 0.1633 m; raw data and null/count audit passed.
- **Limitations:** ID switches may still produce incorrect segments; upstream
  calibration errors remain. Missing true positions cannot be recovered, smoothing
  slightly changes positions, and cross-track identity repair is absent. Real-match
  accuracy and live Redis/PostgreSQL are unverified. Frontend remains unchanged;
  player movement metrics are handled separately in Phase 11.

## Phase 11 — Player analytics

**Status: COMPLETE (backend).**

- **Input and scope:** Only current usable Phase 10 cleaned positions, per Match
  and Track ID. No raw-coordinate fallback, identity linking or upstream CV reruns.
  Existing segment-start semantics and pitch-boundary tolerance are preserved.
- **Metrics:** Euclidean interval distances and summed valid interval duration;
  average = distance / duration, maximum = largest valid interval speed, with
  m/s and km/h. Irregular timestamps are respected. Rejected observations, segment
  breaks and invalid temporal pairs terminate continuity. No P95. Without valid
  intervals, observed distance/duration are zero and speeds are null.
- **Sprints and heatmaps:** Configurable inclusive 7 m/s threshold and 1-second
  minimum continuous duration; summaries reconcile with persisted events. Sparse
  time-weighted occupancy assigns each valid interval's duration to its starting
  cell on the Match's pitch grid (default 20 × 12). Missing intervals add no time.
- **Job, storage and access:** ProcessingJob/RQ `player_analytics`, actual row
  progress, IDs/attempt delivery, safe failure/retry handling, and migration
  `0010_player_analytics`. Four CSVs (players, intervals, sprints, heatmaps) publish
  together with one directory rename under `storage/analytics`. Exact trajectory
  and upstream guards protect results; team changes are independent. Scoped job,
  paginated summary, individual-track and heatmap APIs expose no paths. Admin and
  accessible Coach/Analyst can run/read; Club Management reads; Player is denied.
- **Verification:** 103 Phase 11 tests and 268 related checks passed. Complete
  backend regression: 808 passed, 0 failed, 0 errors, 0 skipped. The earlier WSL
  invocation stalled without a final result; a fresh full run passed after service
  recovery. Ruff lint/format (168 files), FastAPI startup, Alembic current/check,
  populated 0009-to-0010 preservation and four-artifact/API reload audit passed.
  Smoke: Track 3 = 18 m / 3.75 s, average 4.8 m/s, max 8 m/s, one 1-second sprint;
  Track 7 = 8 m / 2.5 s, average 3.2 m/s, max 5 m/s, no sprint. Occupancy equals
  each track's active duration and fractions normalize to one.
- **Limitations:** Track IDs lack automatic roster identity and may split after
  ID switches. Missing movement cannot be recovered; sampling can underestimate
  distance and affects speed. Sprints are methodology-dependent and starting-cell
  occupancy is approximate. Real-match accuracy and live Redis/PostgreSQL remain
  unverified. No frontend, team tactical or ball/event analytics were added.

## Phase 12 — Team tactical analytics

**Status: COMPLETE (backend).**

- **Inputs:** Current usable Phase 10 clean positions and effective Phase 8 labels;
  manual overrides win and Unknown/missing track labels are excluded. Phase 11
  artifacts are independent. No upstream CV or physical analytics are rerun.
- **Method:** Group by exact frame, preserve timestamp, reject duplicate usable
  tracks. Segment boundaries do not remove instantaneous positions. Default minimum
  three visible players per team; insufficient snapshots retain counts and null
  geometry. Unobserved/rejected-only frames are not reconstructed.
- **Metrics:** Mean centroid, Y range = width, X range = depth, mean distance to
  centroid, unique-pair mean spacing, nondegenerate convex-hull area, bounding-box
  area, and centroid separation when both teams are sufficient. Match dimensions
  and physical units are preserved. Summaries average valid snapshots equally,
  exclude nulls, and keep coverage counts; no gap weighting or medians.
- **Job and storage:** ProcessingJob/RQ `team_tactical_analytics`; bounded disk
  regrouping, real row progress, IDs/attempt delivery, safe failures and retries.
  Two CSVs publish as one protected bundle with the shared atomic publisher.
  Migration `0011_team_tactical_analytics` adds only metadata. Exact upstream and
  effective-assignment guards serialize publication with manual corrections.
- **API/access:** Scoped enqueue, both-team summary, team detail and paginated
  series (maximum 100 rows). Admin and accessible Coach/Analyst run/read; Club
  Management reads; Player/anonymous/cross-club requests are denied. No paths.
- **Verification:** 96 focused and 378 related tests passed; complete backend
  regression ran once, 904 passed with no failures/errors/skips (435.47 seconds).
  Ruff lint/format (178 files), FastAPI startup, populated 0010 upgrade and Alembic
  upgrade/current/check passed; development database backup and preservation verified.
  Synthetic smoke: first-frame centroids A `(3.333,3)`, B `(13.333,11)`; each has
  3 players, width 3 m, depth 4 m, compactness 2.306 m, spacing 4 m, hull 6 m²;
  separation 12.806 m. Manual correction, insufficient visibility, protected reload,
  stale publication, failed retries and Phase 11 independence are covered.
- **Limitations:** Visible geometry only; occlusion, Unknown labels, ID switches and
  calibration error affect results. Manual correction may be needed. No inferred
  attacking direction, formations, substitutions, identity or tactical quality.
  Real-match accuracy and live Redis/PostgreSQL remain unverified. No frontend.

## Phase 13 — Frontend analytics dashboard

**Status: COMPLETE.**

- **Route/UI:** Protected, lazy-loaded `/matches/:matchId/analytics`, linked from
  Match Details. Overview, Players/details, Heatmap, Team Tactics and Team
  Assignments reuse the existing design, API client, auth and TanStack Query.
- **Real results:** Backend physical metrics, nullable speeds and observed heatmap
  cells on the shared configurable SVG pitch. X = length; Y = width. Team A/B
  summaries and Recharts width/depth/compactness/centroid series use bounded
  100-snapshot windows and preserve null gaps. No browser metric recomputation.
- **Assignments/jobs:** Explicit Team A/B/Unknown override and clear controls for
  Admin/Coach/Analyst; Club Management reads, Player is denied. Saves reset
  assignments/tactics without invalidating physical analytics. Existing job
  endpoints/polling support explicit generation, progress, failures and retries;
  no automatic pipeline runs. Missing/stale results remain unavailable.
- **Verification:** 40 analytics and 17 affected media tests passed; full frontend
  regression finished with 128 passed, 0 failed, 0 skipped. Final lint, TypeScript
  and production builds passed, including an isolated clean locked install/build.
  The chart dependency stays in the lazy analytics chunk. Edge production review
  passed 22 viewport checks, direct refresh, keyboard controls, all panels,
  overrides/staleness and progress/failures without runtime errors or page overflow.
  Backend unchanged; startup/health, 13 protected contracts and 15 actual Pydantic
  fixture validations passed. No full backend rerun was needed.
- **Limits:** Match tracks are not named players. Heatmaps describe observed
  cleaned occupancy; team geometry depends on visible, correctly assigned tracks.
  Unknown labels and upstream CV errors reduce completeness/accuracy. No attacking
  direction, formations, tactical judgments, ball/event metrics or reports.

## Phase 14 — PDF reports and CSV exports

**Status: COMPLETE.**

- **Implemented:** ReportLab A4 Match PDFs, strict pypdf validation, bounded saved
  heatmaps (default four), all-track tables, Team A/B summaries and limitations.
  Current player/team CSV summaries are generated on demand. Presentation only:
  no CV or analytics calculations and no optional series exports.
- **Lifecycle:** Existing ProcessingJob/RQ with `match_report`, ID/attempt payloads,
  migration `0012_match_reports`, protected attempt-specific report storage and
  atomic publication. Metadata/effective assignments/current result identities
  control staleness, including unavailable-to-available transitions. Partial or
  metadata-only reports label missing analytics; retries preserve earlier PDFs.
- **Frontend and access:** Overview Reports / Exports panel, explicit generation,
  job polling, current/stale/failure states and authenticated Blob downloads.
  Admin/Coach/Analyst generate within existing scope; Management reads/downloads;
  Player/anonymous/cross-club requests are denied.
- **Verified:** 62 focused backend checks; final backend **961 passed**;
  frontend **143 passed**, including 55 focused report/dashboard tests. Migration
  preservation/check, Ruff/format, FastAPI, ESLint, TypeScript and build passed.
  Saved-input PDF/CSV smoke, all page types in a 50-track PDF, 18 browser viewport
  checks and three downloads passed; clean installation of the declared PDF stack
  passed. Formula injection, nulls, axes, freshness, permissions and failure cleanup
  are tested. Real-match CV accuracy remains unassessed by reports.

## Phase 15 — Computer-vision evaluation

**Status: COMPLETE. Phase 16: OPTIONAL / DEFERRED.**

- **Implemented:** Existing isolated evaluator extended with the inspected
  SoccerNet-GSR 1.3 adapter, lossless preparation and bounded orchestration of
  unchanged production YOLO, ByteTrack and automatic jersey classification.
- **Real evidence:** Official SN-GSR-2025 validation release, pinned revision;
  SNGS-021/039/078 from games 2/3/5, selected by sorted metadata before inference.
  All 37 duplicate-game skips are recorded. First 150 consecutive frames each:
  450 frames, 18 seconds, 6,603 scored player/GK boxes, 49 GT/team identities,
  642 ignored referee boxes. All 450 production-decoded frames are pixel-identical
  to source JPEGs; early/middle/late GT overlays align.
- **Integrity:** Jersey-color references extracted from human-labelled SoccerNet
  team annotations freeze A/B mapping; no manual overrides, best permutation,
  threshold tuning or repeated first-clip YOLO. Source/config/weights/artifact
  hashes and per-clip runtime are preserved outside SQLite/Git.
- **Results:** Detection precision/recall/F1 88.64%/85.45%/87.01%, AP50 81.40%;
  tracking IDF1 76.44%, MOTA 73.09%, MOTP distance 0.2065, 58 ID switches.
  Automatic team accuracy/coverage 6.12%, Unknown 93.88%; classified-only 100%
  covers just three identities. Poor results remain visible and unchanged.
- **Unavailable:** Calibration and pitch-coordinate accuracy lack verified fit
  and separate held-out correspondences; moving camera poses are not inferred.
  No misleading coordinate CSV or invented metre-error results are produced.
- **Runtime:** WSL2/i5-1250P CPU, torch 2.14.1+cpu, CUDA=False. Recorded stages plus
  model construction total 200.510 seconds; detection averages 9.068 FPS including
  decoding/I/O. Complete results and limitations are linked from README.
- **Verified:** 118 focused tests, 227 CV regressions, one full backend run:
  **1,079 passed, 0 failed/errors/skipped**. Ruff/format (208 files), evaluation
  CLI and WSL FastAPI startup pass. No frontend tests or production CV changes.
- **Limits:** Three six-second broadcast clips do not establish full-match or
  arbitrary user/5v5 performance. Low automatic team coverage and unavailable
  coordinate validation are explicit. No Phase 16 work has started.

## Phase 16 — Optional ball detection/tracking

**Status: OPTIONAL / DEFERRED.** Pretrained ball detection/tracking is not required
for the core FYP and was intentionally excluded from the final scope. No ball
model, tracking stage or ball-dependent output is claimed.

## Phase 17 — Optional possession/pass/shot inference

**Status: OPTIONAL / DEFERRED.** This depends on sufficiently reliable Phase 16
ball tracking and is outside the validated final core scope. Possession, passes,
shots and xG are not implemented or inferred.

## Phase 18 — Final integration testing and documentation

**Status: COMPLETE.** Final core: Phases 1–15 plus Phase 18; Phases 16–17 remain
**OPTIONAL / DEFERRED**, intentionally outside the validated core scope.

- **Setup:** Fresh WSL CPU environment and frontend dependency installation,
  temporary base/head/base/head migrations, unique `0012_match_reports` head,
  no schema drift, secure/idempotent admin bootstrap and real API startup.
- **Live integration:** Real Redis/RQ JSON delivery and all nine job types;
  queue-unavailable failure, worker failure/retry, scoped roles and team-edit
  staleness. The controlled 50-frame still-image football clip produced detection,
  tracking, assignments, coordinates, cleaning, physical/tactical analytics and
  PDF/CSV. It is explicitly not a real-motion or coordinate-accuracy benchmark.
- **Final verification:** One full backend run: **1,079 passed**, no failures,
  errors or skips, **600.96 seconds**, four existing JUnit metadata warnings.
  **231 focused backend checks** passed. Final frontend: **143 passed**, ESLint,
  TypeScript and production build passed. Ruff and format (211 files), structure,
  migration and health checks pass. **55 live browser checks**, **40 fixture
  viewport checks**, and all **eight rendered PDF pages** passed review.
- **Fix:** Home-page text no longer incorrectly claims analytics are unavailable.
  Its regression now checks the implemented tools, access/processing conditions,
  match navigation and absence of automatic processing. Algorithms, thresholds,
  backend functionality and migration history remain unchanged.
- **Documentation:** README provides verified WSL CPU install/service/check
  commands; DEMO_GUIDE.md provides the presentation sequence;
  docs/ARCHITECTURE.md defines metrics, boundaries and dependencies;
  docs/PHASE18_VERIFICATION.md separates live evidence, fixtures and reused data.
- **Integrity:** Development DB and `.env`, production CV files, existing YOLO
  weights and frozen Phase 15 results are preserved. Runtime output is ignored.
  Source-tree credential/hygiene checks pass; this folder has no Git metadata,
  so no commit-history audit is claimed. Isolated QA services were stopped.
- **Limitations retained:** Static-camera assumptions, unavailable independent
  coordinate accuracy, poor jersey coverage, small 18-second evaluation sample,
  non-real-time CPU performance and unvalidated PostgreSQL/ffprobe deployment.

Final core flow: video -> calibration -> player detection -> tracking -> team
assignment -> coordinate mapping -> trajectory cleaning -> player analytics ->
team tactical analytics -> dashboard -> reports/exports. No ball tracking,
possession/pass/shot inference or fabricated xG was introduced.

## Administrator-approved signup (post-core addition)

**Status: COMPLETE.** Public `/signup` creates a pending access request. An
administrator reviews it under Access requests and approves the requested
non-admin role with optional club membership, or rejects it. The initial signup
verification below predates the role-hardening addition documented next. Only
approval creates a login account;
existing accounts and resource authorization remain unchanged. Reviews keep an
audit history, discard request credentials after review, and prevent duplicate
or competing decisions from overwriting accounts. No email verification or
notification service was added; applicants contact their administrator.

- **Migration:** Additive `0013_signup_requests`; unique head/current and schema
  check passed. Applied to the backed-up development database with every existing
  row unchanged, including the saved match and its nine processing jobs.
- **Backend:** 90 signup/auth/users/migration checks passed; 47 additional club
  authorization and populated-database migration checks passed (137 total).
  Ruff and formatting passed. The full CV suite was not rerun for this addition.
- **Frontend:** 158 tests passed with `npm.cmd test -- --maxWorkers=2`; ESLint,
  TypeScript and production build passed. An initial concurrent run timed out in
  one existing analytics test; the two-worker rerun passed without analytics
  changes. All 15 new signup UI tests passed.
- **Live browser:** 27 checks passed against a disposable real FastAPI database
  and production frontend preview, including signup, pending login denial,
  approval, selected club access, rejection, history, logout and admin-route
  denial. Desktop/390px/320px screenshots had no horizontal overflow or browser
  errors. QA accounts were isolated from development data; QA services stopped.
- **Scope preserved:** Phases 16-17 remain OPTIONAL / DEFERRED; frozen Phase 15
  evaluation and existing CV/analytics outputs were neither changed nor rerun.

## Post-Phase-18 hardening / polish

**Status: implementation and documentation finalized.** Targeted post-fix
verification passed; the complete backend suite was not rerun after the migration
fix. Core phase statuses above are unchanged. Phases 16–17 remain OPTIONAL /
DEFERRED. No ball/event work was added.

- Required requested-role signup; exact-role admin approval; legacy requests kept.
- Authoritative preparation reuse, preserved retries/history and compact UI states.
- Reproducible cached 60-second stride-5/stride-1 comparison. Full cadence alone
  did not prove better continuity. Conservative offline stitching accepted zero
  merges and was rejected for production; original track IDs remain intact.
- Honest heatmap coverage, uniform valid-crop sampling, classifier diagnostics,
  and versioned user-seeded team-color setup with manual override precedence.
- Separate layered software-architecture and CV-pipeline SVGs; responsive UI,
  consistent job badges, real browser signup/approval and color-setup verification.
- Migrations 0014/0015 applied only after backup and populated-copy rehearsal;
  all old-column data preserved. Current unique head: `0015_team_color_prototypes`.
- Initial full backend run: **1,177 passed, 7 failed, 0 errors/skips**, **755.47 s**,
  four JUnit metadata warnings. All seven failures shared migration 0015's SQLite
  downgrade/FK cause. Post-fix manual verification: **92 coordinate/report tests
  passed**, plus **3 remaining affected migration tests passed**. These targeted
  checks are not a clean full-suite rerun.
- Migration 0015 now detaches/restores the incoming assignment FK around SQLite
  parent-table rebuilding and refuses downgrade with team-color history. Existing
  rows/manual overrides are preserved; older migrations remain unchanged.
- Alembic current/check and empty `PRAGMA foreign_key_check` verified. Ruff passed;
  formatting reported **228 files already formatted**. Frontend **175 passed**,
  ESLint/TypeScript/build passed; browser **77 checks passed**; SVGs visually checked.
- Tracking fragmentation, zero accepted stitches, sparse seeded classification
  (3/251 at full cadence), Unknown labels and static-camera limits remain explicit.
- Exact measurements, evidence sources and caveats: [docs/HARDENING.md](docs/HARDENING.md).

## UI redesign (post-core, branch `feature/ui-redesign`)

**Status: Stages 0–9 implemented on `feature/ui-redesign`; awaiting owner review
before any merge to `main`.** Presentation only: routes, API contracts, RBAC,
CV/analytics calculations and the backend are unchanged.

- Stages 0–3: design tokens and shared UI, application shell and navigation,
  dashboard.
- Stage 4: match list/header and the evidence-based processing pipeline.
- Stage 5: analytics workspace (overview, players, tactics, processing, reports).
- Stage 6: detection/tracking review with processed-frame navigation.
- Stage 7: shared metre-accurate pitch, calibration workspace, heatmap legend and
  team centroid paths.
- Stage 8: sign-in, users, access requests, clubs, teams, players and squads.
- Stage 9: final QA, frame-navigation focus fix, sidebar scrolling on short
  screens, vendor chunk split, documentation, browser, security and end-to-end
  CV verification.
- Stage record, checkpoint log and verification results:
  [docs/UI_REDESIGN.md](docs/UI_REDESIGN.md).
