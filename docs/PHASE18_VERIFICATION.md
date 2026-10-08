# Phase 18 verification record

Status: **COMPLETE** (6 October 2026). Core scope: Phases 1–15 plus Phase 18.
Final machine-readable summary: `.tools/phase18/verification.json`.

This is the historical Phase 18 baseline. Later signup/hardening migrations and
verification results are recorded separately in [HARDENING.md](HARDENING.md),
including the distinction between the initial full backend run and targeted
post-fix checks. Counts and migration versions below describe the original run.

This record separates integration evidence from scientific evaluation. Production
CV algorithms/settings and the frozen Phase 15 evaluation were not changed.
The home page had obsolete copy claiming analytics were unavailable; it now
describes implemented match tools with access/processing requirements. Its old
test was updated to verify the current guidance, Matches navigation and absence
of automatic processing, retaining a negative assertion against the obsolete claim. Phases 16 and 17 are intentionally **OPTIONAL / DEFERRED**.

## Environment and evidence locations

- Workspace: `D:\VS Projects\FYP_Footlytics` / `/mnt/d/VS Projects/FYP_Footlytics`.
- Existing runtime: `/home/sabeeh/.venvs/footlytics-yolo`, Ubuntu WSL2,
  Python 3.14.4, torch 2.14.1+cpu, CUDA unavailable, Ultralytics headless 8.4.170.
- Fresh installation: `/home/sabeeh/.venvs/footlytics-phase18-clean`, no system site
  packages, installed with `backend/requirements-wsl-cpu.lock`; `pip check`, torch,
  Ultralytics, ReportLab and FastAPI imports passed. Existing runtime retained.
- Redis 8.0.5 was installed because no Redis server was present. Live QA used an
  isolated loopback port, queue `video-processing` and the production JSON serializer.
- Windows Node 24.21.0; fresh `npm ci` completed. Linux and Windows venvs are separate.
- Main live evidence: `.tools/phase18/live-20261006T053551Z/`.
  `.tools/phase18/latest-run.txt` points to this run. `results.json` contains live
  checks, job records/progress, saved summaries, manual corrections and CSV headers.
  `browser/results.json` contains actual live browser results and screenshot names.
  `rendered/` contains all eight rendered PDF pages.
- Focused JUnit: `.tools/phase18/focused.xml`; full JUnit:
  `.tools/phase18/full-backend.xml`. Final static checks and preserved hashes are
  recorded in `.tools/phase18/final-checks.json` and `baseline.json`.
- Local QA helpers and ephemeral credentials are under ignored `.tools/`; they are
  machine-local evidence, not fresh-install dependencies or published credentials.

## Clean installation, schema and bootstrap

A fresh temporary SQLite database was upgraded from base to the unique head
`0012_match_reports`, checked for drift, downgraded to base and upgraded again.
There are 14 expected production tables and five seeded roles. Evaluation creates
no production tables. Alembic `heads`, `current` and `check` pass. These operations
used the QA database; the development database's SHA-256 remains unchanged.

The real `scripts/create_admin.py` created an administrator after migrations and
was idempotent for the same active administrator. Boundary checks accepted 8 and
128 character passwords, rejected 7 and 129, and confirmed no password appeared
in captured stdout/stderr. Passwords were random ephemeral environment inputs;
the CLI's interactive path uses secure double prompts. Login and role assignment
were verified through HTTP. No public registration route exists.

The existing WSL API ran with:

```bash
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 18800
```

For QA, process environment variables selected a separate database, storage,
Redis port and JWT secret. The regular documented demo port is 8000. The development database revision
was also read without mutation and is `0012_match_reports`. `/docs`,
`/api/health`, auth and protected domain routes passed. API import needs no torch
initialization; ReportLab imports in both validated Linux environments.

## What ran live

All of the following ran in Phase 18 through actual HTTP, Redis and separate
`python scripts/run_worker.py --burst` processes. Workers received only integer
job IDs and attempt numbers; there was no injected queue or synchronous fallback.

1. Admin login; users with all five roles; two clubs, four teams, a linked Player,
   squad membership and matches. An inactive login was rejected.
2. Invalid video rejection and valid football-source upload/metadata validation.
3. Real Redis-unavailable 503 and persisted failed job, followed by retry after
   Redis startup. A worker with a temporarily missing **QA-owned** source failed
   safely; restoring that file and retrying succeeded. Originals were not moved.
4. A calibration JPEG was decoded; invalid timestamps and incomplete points were
   rejected. A Coach saved a valid four-point calibration.
5. Real YOLO detection → ByteTrack → jersey classification → explicit manual team
   corrections → coordinate mapping → cleaning → player analytics → team tactics.
6. Detection/tracking summaries and real protected JPEG previews were loaded.
7. An eight-page PDF and both CSV exports were generated by production code and
   downloaded through authenticated endpoints. Browser downloads were also checked.
8. An effective assignment change made tactics/report stale while physical player
   analytics remained identical and the previous PDF remained intact. Restoring
   the identical effective map restored the matching current fingerprint.

The input was **50 repeated copies of SNGS-039 image 000001 at 25 FPS**, a two-second
controlled static football clip, with pixel-identical PNG/MOV decoding. The match,
filename and PDF explicitly say controlled still-frame integration. Four visible
small-goal-area corners were read from that image's human line annotations; pitch
model 105 × 68 m, goal-area depth 5.5 m and width 18.32 m. The goal-area dimensions
follow [IFAB Law 1](https://www.theifab.com/laws/latest/the-field-of-play/).
This is an annotation-assisted fitting smoke, **not independent coordinate
accuracy**, and no homography was fitted to player GT positions. Manual team
corrections used first-frame annotation/box matches and are separate from the
saved automatic classification outputs.

Measured integration outputs: **950 detections, 950 tracked rows, 19 track IDs,
750 usable cleaned observations and 200 retained unusable observations**. Four
tracks have no usable pitch observations; null speeds and empty heatmaps remain
honest. Both teams had 50 valid tactical snapshots after explicit manual assignment.
Stationary distance values are expected for a repeated image; these are not a
real player movement benchmark. Detection/tracking warn that four complete pitch
corners are absent, so ROI filtering is not invented. Other warnings record weak
jersey evidence, unusable rows and the absence of ffprobe.

The original moving SNGS-039 150-frame clip was uploaded and prepared in a second
match. It was deliberately left uncalibrated. A partial report correctly states
that analytics are unavailable. The moving clip did not run the CV/analytics chain
again. Existing Phase 15 weights, source media and frozen evaluation outputs were
reused; the evaluation was neither changed nor rerun. No full match was processed.
After the user's continuation instruction, all successful CV/report artifacts were
reused; there was no repeat detection, tracking or analytics processing.

## Browser and PDF review

- **49 live browser checks**, no API interception, no runtime JS errors, at
  1440 × 1000, 390 × 844 and 320 × 844. Login failure/success, same-tab reload,
  protected redirect/logout, primary navigation/domain pages, detection/tracking
  previews, saved calibration, analytics tabs, usable and unavailable heatmaps,
  assignments, role-aware navigation and three protected downloads passed.
  No page-wide horizontal overflow was observed; wide tables use bounded scroll.
- After the home-page correction, **six additional live production-build checks**
  verified home guidance and saved player metrics at the same three widths.
  Total live browser checks: **55**, zero runtime errors. The final screenshots
  are under `browser-final/`; no CV or analytics stage was rerun.
- Existing Phase 13 browser script: **22 viewport checks** using explicitly labelled
  fixtures. Its old fixture needed the Phase 14 report-status endpoint; the correct
  empty report DTO was added while keeping all assertions and unexpected-request
  checks. Evidence: `.tools/browser-check/phase13-1791295615712/`.
- Existing Phase 14 browser script: **18 viewport checks**, three fixture-backed
  downloads, zero runtime/unexpected errors. It covers missing/current/stale,
  generating/failed and Management states at three widths. Evidence:
  `.tools/browser-check/phase14-1791295631901/`.
- The real PDF passed strict parsing and all **eight pages were rendered and
  visually inspected**. Headers, match/pitch metadata, numbering 1–8, repeated
  table layout, four bounded heatmaps and limitations text are readable. No
  clipping or overlap was observed. Unavailable speeds use an explained dash;
  narrative is descriptive methodology, not invented football events.
- CSV nulls, signed numeric values and formula-text protection are verified by
  the focused report tests; live CSV schemas and protected downloads also passed.
  Historical PDF preservation and failed-retry safety remain covered.

## Failure paths, access and dependency evidence

| Check | Evidence |
| --- | --- |
| Invalid/inactive login | Live API; invalid login also in desktop/mobile browser |
| Missing video, invalid upload | Live HTTP rejection |
| Missing/partial calibration, negative timestamp | Live HTTP rejection; existing calibration tests |
| Redis unavailable | Real refused connection: 503, durable failure, no synchronous processing |
| Worker failure/retry | Real RQ execution with temporarily absent QA source, then restored-source retry |
| Unavailable analytics / partial PDF | Separate uncalibrated moving-clip match and parsed partial report |
| Null metrics/empty heatmap | Real rejected track in live browser and PDF |
| Anonymous and foreign clubs | Live API denials and focused backend tests |
| Coach/Analyst | Scoped calibration/detection/tracking/team-edit operations live |
| Club Management / Player | Direct backend mutation denials; Management reads exports, Player cannot read arbitrary track analytics |
| Video/calibration/tracking staleness | Existing regression contracts; no new dependency model |
| Effective team changes | Live invalidation; physical results and historical PDF preserved |
| Retry/artifact/PDF failure safety | Focused job/report regressions plus live worker retry |
| Report/analytics UI failures | Existing fixture browser scripts, explicitly distinct from live evidence |

Metric definitions were checked against backend code and focused tests. Player
metrics use cleaned same-segment positive-time intervals; heatmaps are time
weighted. Tactics use X length/Y width, exclude Unknown, and retain null geometry
when insufficient. Frontend code formats/sorts supplied metrics; it does not
replace backend distance/speed/geometry calculations. See ARCHITECTURE.md.

## Automated checks

| Check | Result |
| --- | --- |
| Focused backend/integration | 231 passed, 0 failures/errors/skips, 124.87 s; 2 existing JUnit metadata warnings |
| Additional focused frontend diagnosis | 40 analytics tests passed unchanged, 11.75 s |
| Complete frontend suite | 143 passed, 8 files, 0 failed/skipped; 45.54 s, using `npm test -- --maxWorkers=1` |
| ESLint | Passed |
| TypeScript + production build | `npm run build` (`tsc -b && vite build`) passed; Vite build 4.02 s |
| Ruff | Passed from the established `backend/` working directory |
| Ruff format | 211 files already formatted |
| Structure | Passed |
| Unique/current Alembic head | `0012_match_reports`; no drift |
| API import/startup/health | Passed in WSL |
| Full backend regression | **1,079 passed; 0 failures/errors/skips; 600.96 s; 4 existing JUnit metadata warnings; one run against the final backend state** |

The first frontend run overlapped other expensive checks and one test timed out
at its unchanged five-second limit (142 passed). That test's full 40-test file
passed alone. The complete unchanged suite then passed serially; no timeout or
assertion was relaxed. A later final content review found the obsolete home-page text. After that small
frontend source/test correction, the full frontend suite, lint and build were
rerun as required. No CV processing or backend code changed because of it. The revised test
initially used an unsupported Testing Library option; TypeScript caught it and
the equivalent anchored-name matcher passed the final full checks. Early local QA-helper assertions about JSON
empty arguments and selection of a track without occupancy were corrected; these
were verification-helper assumptions, not production defects. A root-directory
Ruff invocation misclassified imports; documentation now uses the repository's
established backend-directory command without rewriting working imports.

## Source integrity and hygiene

Read-only inspection covered 312 source/config/documentation files before this
record was added. High-confidence secret patterns produced zero findings; a
literal credential assignment scan found only an explicit frontend test fixture.
Actual `.env` and ephemeral QA credentials remain ignored. `.gitignore` covers
local tooling, virtual environments, dependencies, SQLite/Redis output, caches,
logs, builds, models, videos and runtime data/storage. No unintended large source
file was found and no legitimate evaluation/test asset was removed.

This workspace has **no Git metadata** (and native Git is absent); WSL Git also
reports no worktree. The audit therefore covers the available source tree, not a
nonexistent Git index or remote commit history. Before publishing, review the
actual repository/index on the machine used for version control.

Baseline hashes confirm the development database, root `.env`, all production CV
source files and the frozen Phase 15 evaluation summary are unchanged. Phase 15
artifacts/provenance remain in their original locations. No application algorithm,
threshold, frontend feature, migration history or scientific evaluation was changed.

## Limits retained for the final presentation

Static/planar calibration cannot compensate for moving broadcast cameras, and
independent coordinate accuracy remains unavailable. Automatic jersey coverage on
SoccerNet was poor and is not hidden. CPU operation is not real time. Only 18
seconds from three broadcast 11v11 games were evaluated; this does not establish
broad 5v5/user-footage/full-match performance. Ball/event analytics are deferred.
PostgreSQL and external ffprobe were not live-validated; OpenCV fallback was.
The isolated QA API/Redis processes were stopped after successful verification;
all evidence was preserved. Use DEMO_GUIDE.md to launch the normal application.
