# FOOTLYTICS

**Football Video Analytics Platform Using Computer Vision**

FOOTLYTICS is a post-match football video analytics FYP. It manages recorded
11v11/5v5 matches, detects and tracks players, maps calibrated ground points into
pitch metres, displays physical and team geometry analytics, and exports PDF/CSV
reports. Results depend on visible players, usable calibration and current inputs;
missing data remains Unknown or Unavailable. Validation limits are stated below.

## Current status

Phases 1–15 are complete. Phases 8–12 provide backend results, now visualized by
the Phase 13 analytics dashboard. Authentication,
administration and club-scoped football
management now include validated match-video upload, explicit replacement,
protected file access and durable background preparation jobs. Matches support
11v11/5v5 with individually configured pitch dimensions. Backend homography and
the manual pitch-calibration frontend are complete. YOLO detection and ByteTrack
tracking include protected summaries and selected-frame visual review;
CPU runtime setup is documented below. Backend jersey classification now provides
track-level team assignments and manual override APIs. Saved tracks can now be
mapped through the current calibration into pitch coordinates in metres.
Separate cleaned trajectories retain raw observations for auditing.
Track-scoped player analytics now provide observed distance, speeds, sprints and
time-weighted heatmap data. Team analytics provide visible-team centroids, width,
depth, compactness, spacing and area. The Match Analytics dashboard displays these
results and supports manual team corrections. Match PDFs and player/team CSV
exports present the same saved results without rerunning CV or analytics.
Missing analytics always use an empty state.

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for all 18 phases and
[AGENTS.md](AGENTS.md) for persistent development rules.
**Phase 5 — COMPLETE. Phase 6 — COMPLETE. Phase 7 — COMPLETE. Phase 8 — COMPLETE. Phase 9 — COMPLETE. Phase 10 — COMPLETE. Phase 11 — COMPLETE. Phase 12 — COMPLETE. Phase 13 — COMPLETE. Phase 14 — COMPLETE.**
**Phases 1–15 — COMPLETE. Phases 16–17 — OPTIONAL / DEFERRED. Phase 18 — COMPLETE.**

The final core scope is Phases 1–15 plus Phase 18 integration and QA. Ball
tracking and possession/pass/shot inference are intentionally deferred. Start with
the setup below, then use [DEMO_GUIDE.md](DEMO_GUIDE.md). See
[architecture and dependencies](docs/ARCHITECTURE.md) for the complete pipeline.

## Architecture

```text
React frontend -- REST --> FastAPI -- enqueue --> Redis / RQ
                            |                      |
                        SQLAlchemy             Python worker
                            |                      |
                          SQLite <--- metadata/results
                                                   |
                                      video preparation / CV
                                      cleaning / player analytics
                                                   |
                                                storage/
```

The API validates uploads with bounded metadata/frame inspection. Processing
requests persist a job, submit its identifiers to RQ and return without waiting
for processing. A separate Python worker reopens the stored video, verifies its
metadata and records progress; the frontend polls active jobs. Video bytes live
in storage, with metadata and relative paths in the database.

Backend packages separate HTTP routes (`api`), business logic (`services`), ORM
entities (`models`), validation (`schemas`), security (`auth`), processing (`cv`,
`analytics`, `workers`) and exports (`reports`). Frontend screens go in `pages`,
feature code in `features`, reusable UI in `components`, and REST access in `api`.

## Stack

- Frontend: React 19, strict TypeScript, Vite, React Router, TanStack Query,
  Tailwind CSS and Recharts. Add shadcn/ui when useful without duplicating existing UI.
- Backend: Python 3.12+, FastAPI, Pydantic / pydantic-settings, SQLAlchemy and
  Alembic, PyJWT, pwdlib with Argon2id, and email-validator.
- Development database: SQLite; portable SQLAlchemy models will allow PostgreSQL
  later. Authentication and football-domain records are persisted now.
- Preparation: Redis + RQ with JSON serialization and a separate worker;
  python-multipart, OpenCV headless and NumPy for lightweight video validation.
  External ffprobe is preferred for metadata and configurable through settings.
- Detection: pretrained [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/),
  using `ultralytics-opencv-headless` (validated WSL CPU lock: 8.4.170,
  [AGPL-3.0](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)).
  ByteTrack uses the same Ultralytics stack plus `lap` for assignment. Movement
  analytics consume saved cleaned trajectories. No training pipeline is included.
- Verification: pytest, Ruff, Vitest, React Testing Library, TypeScript and ESLint.

`DEVICE=auto` selects CUDA when PyTorch reports it available, otherwise CPU.
`DEVICE=cpu` forces CPU; explicitly requested unavailable CUDA fails safely.

## Structure

```text
FYP_Footlytics/
|-- frontend/
|   |-- src/
|   |   |-- api/ assets/ components/ features/ hooks/
|   |   |-- layouts/ pages/ routes/ test/ types/ utils/
|   |   `-- App.tsx, main.tsx, styles.css
|   `-- package.json, package-lock.json, vite.config.ts, tsconfig*.json
|-- backend/
|   |-- app/
|   |   |-- api/ analytics/ auth/ core/ cv/ database/ evaluation/
|   |   |-- models/ reports/ schemas/ services/ workers/
|   |   `-- main.py
|   |-- alembic/versions/ (0001_users_and_roles through 0015_team_color_prototypes)
|   |-- tests/
|   `-- alembic.ini, requirements*.txt, requirements-dev.lock, requirements-wsl-cpu.lock, pyproject.toml
|-- storage/
|   `-- raw/ processed/ tracks/ analytics/ calibration/ reports/ exports/
|-- data/
|   `-- validation_clips/ annotations/ sample/
|-- scripts/check_structure.py, scripts/create_admin.py, scripts/run_worker.py
|-- docker/
|-- docker-compose.yml
|-- .env.example
|-- .gitignore
|-- AGENTS.md
|-- README.md
`-- IMPLEMENTATION_PLAN.md
```

Empty directories use `.gitkeep`. Runtime storage and data contents are ignored.
Later, deliberately versioned small fixtures belong under `backend/tests/fixtures`
with documented provenance. Do not force-add match footage or model weights.

## Local setup

The validated backend/CV runtime is **Ubuntu under WSL2, Python 3.14.4, CPU
PyTorch 2.14.1+cpu and Ultralytics headless 8.4.170**. Run the API and RQ worker
in the same Linux environment. Native Windows previously failed initializing
PyTorch `c10.dll`; its Python environment is not the supported complete runtime.
Node 22.13+ (22.x) or Node 24+ is required; Node 24.21.0 was verified on Windows.
SQLite is the verified development database. Redis is required for processing.

On Windows PowerShell, verify the existing distribution before installing anything:

```powershell
wsl --status
wsl -l -v
wsl -d Ubuntu
```

Ubuntu must show version 2. For a machine without WSL, install Ubuntu with
`wsl --install -d Ubuntu`, restart Windows if requested, and complete Ubuntu user
setup. Reuse an existing distribution and working virtual environment.

### Fresh backend installation (Ubuntu terminal)

These commands assume Python 3.14 with its `venv` module is installed. Keep the
Linux environment under your Linux home for performance; source remains on D:.
`backend/requirements-wsl-cpu.lock` captures the existing validated CPU environment.
The general development lock is retained for history; use the CPU lock for this
WSL workflow. Install CPU wheels from the [official PyTorch CPU index](https://pytorch.org/get-started/locally/)
first, then install the remaining exact pins without replacing satisfied packages.

```bash
cd "/mnt/d/VS Projects/FYP_Footlytics"
python3.14 -m venv "$HOME/.venvs/footlytics-yolo"
source "$HOME/.venvs/footlytics-yolo/bin/activate"
python -m pip install torch==2.14.1+cpu torchvision==0.29.1+cpu --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r backend/requirements-wsl-cpu.lock
python -m pip check
python -c "import torch, ultralytics, reportlab; print(torch.__version__); print(torch.cuda.is_available())"
```

Create the environment only when it does not already exist. On this workstation,
`/home/sabeeh/.venvs/footlytics-yolo` is the existing runtime. Phase 18 also checked
a fresh independent environment at `/home/sabeeh/.venvs/footlytics-phase18-clean`.
CPU inference is sufficient; CUDA is optional. The first detection job resolves
`yolo11n.pt` into `storage/models/` and may need network access. Reuse existing
weights, or set `YOLO_MODEL` to a local `.pt` file. Do not download a second model
just to start the API.

### Configure, migrate and create an administrator

From the repository root in the activated Ubuntu environment:

```bash
# Fresh clone only: preserve any existing .env.
test -f .env || cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated value in `JWT_SECRET` in `.env`, keeping it private. The example
secret intentionally fails startup validation. Review `.env.example`; default
`DATABASE_URL=sqlite:///./storage/footlytics.db`, `STORAGE_DIR=./storage`,
`REDIS_URL=redis://localhost:6379/0` and `RQ_QUEUE_NAME=video-processing` work for
this local setup. API and worker must share these values. Then run:

```bash
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
python scripts/create_admin.py --email admin@example.com --name "FOOTLYTICS Admin"
```

Choose the password at the secure prompts; there is no default password. The
current unique migration head is `0015_team_color_prototypes`. Never downgrade the
development database to check migrations: pytest uses temporary databases.

### Start Redis, API and worker (separate Ubuntu terminals)

Install Redis only if missing: `sudo apt-get update` followed by
`sudo apt-get install -y --no-install-recommends redis-server`.
If `redis-cli ping` returns `PONG`, reuse that running server. Otherwise start it:

```bash
redis-server --bind 127.0.0.1 --port 6379
```

This foreground terminal is the Redis service. The existing optional Docker
alternative is `docker compose up -d redis` from the root when Docker is installed;
use one Redis service on this port. Redis 8.0.5 was verified in WSL.

API terminal:

```bash
cd "/mnt/d/VS Projects/FYP_Footlytics"
source "$HOME/.venvs/footlytics-yolo/bin/activate"
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Worker terminal:

```bash
cd "/mnt/d/VS Projects/FYP_Footlytics"
source "$HOME/.venvs/footlytics-yolo/bin/activate"
python scripts/run_worker.py
```

The official worker wrapper uses queue `video-processing`, JSON serialization,
and shared settings. Add `--burst` to exit after queued jobs finish. Workers
receive job IDs and attempt numbers, create their own sessions, and persist safe
failures. An unavailable Redis service returns an error and never starts CV in
an HTTP request. Native Windows workers are deliberately rejected.

### Start the frontend (Windows PowerShell)

```powershell
Set-Location 'D:\VS Projects\FYP_Footlytics\frontend'
npm.cmd ci
npm.cmd run dev
```

For this workstation's bundled Node, first run from the repository root:

```powershell
$nodeTools = Get-ChildItem .tools/node -Directory | Select-Object -First 1
$env:Path = $nodeTools.FullName + ';' + $env:Path
```

A fresh developer installs Node normally; `.tools` is ignored machine-local
output. `npm ci` respects `frontend/package-lock.json`.

- Frontend: <http://127.0.0.1:5173>; sign in at `/login` with your chosen admin.
- API liveness: <http://127.0.0.1:8000/api/health>.
- API documentation: <http://127.0.0.1:8000/docs>.

Check health with `curl http://127.0.0.1:8000/api/health` in Ubuntu or
`Invoke-RestMethod http://127.0.0.1:8000/api/health` in PowerShell. It reports
liveness only; it does not test Redis or CV readiness. Vite proxies `/api` to
`API_PROXY_TARGET` (default `http://127.0.0.1:8000`). API base is
`VITE_API_BASE_URL=/api`. If Windows localhost forwarding is unavailable, set
`API_PROXY_TARGET` to the Ubuntu IP and restart Vite; keep the API bound to
`0.0.0.0`. Never put secrets in `VITE_*` variables.

## Configuration

`backend/app/core/config.py` is the single backend settings source. It reads the
root `.env`; actual environment variables take precedence. Relative storage and
SQLite file paths are resolved against the repository root, independent of the
working directory. Settings loading creates no directories, tables or connections.
Authentication, upload, queue and YOLO/device settings are active. Processing
profiles remain reserved for later work.

| Setting | Default / meaning |
| --- | --- |
| `STORAGE_DIR` | `./storage`; application-owned media root |
| `MAX_UPLOAD_SIZE` | `2147483648` bytes (2 GiB); exact file limit, including chunked requests |
| `FFPROBE_PATH` | `ffprobe`; executable name or administrator-configured path |
| `VIDEO_INSPECTION_TIMEOUT_SECONDS` | `30` per metadata/decode subprocess |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `RQ_QUEUE_NAME` | `video-processing` |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | `2` for connection and socket operations |
| `RQ_JOB_TIMEOUT_SECONDS` | `120` for a preparation attempt |
| `RQ_RESULT_TTL_SECONDS` | `86400` for RQ success/failure records; SQL job history remains |
| `YOLO_MODEL` | `yolo11n.pt`; pretrained detection weights or a local `.pt` path |
| `YOLO_CONFIDENCE` | `0.25`; reported detections (counts, overlays) are at or above this threshold; boxes down to `TRACK_LOW_THRESH` are also stored for tracking only |
| `YOLO_IMAGE_SIZE` | `640`; inference size, a multiple of 32 |
| `DEVICE` | `auto`; also accepts `cpu`, `cuda` or `cuda:N` |
| `DETECTION_FRAME_STRIDE` | `1`; infer every Nth decoded frame |
| `DETECTION_ROI_ENABLED` | `true`; filter only when all four pitch corners are supplied |
| `DETECTION_JOB_TIMEOUT_SECONDS` | `21600`; six hours per detection attempt |

Install an FFmpeg distribution that includes `ffprobe`, place it on the process
PATH or set `FFPROBE_PATH`, then check `ffprobe -version`. With ffprobe absent,
OpenCV supplies validated dimensions, FPS and frame count, and estimates duration
as frame count / FPS. Codec and container fields remain null/Unavailable and the
API displays a warning. Corrupt probe output never triggers this fallback.

Vite reads the same root environment directory but exposes only `VITE_*` values
to the browser. Never put secrets in those variables. `/api` requests are proxied
to `API_PROXY_TARGET` during development. For deployment, configure a reverse
proxy or set `VITE_API_BASE_URL` to the backend API base at build time. If changing
`API_PREFIX`, also align the frontend base URL and development proxy path.

The API refuses to start with a missing, weak or example JWT secret. Generate a
random value and place it in `JWT_SECRET` in the root `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep that value private. The example secret is deliberately unusable. Tokens use
HS256 and expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60). Changing the
secret invalidates all existing tokens. Migrations and admin creation do not need
the signing secret; the running API does. Credentials, real `.env` files and
runtime outputs stay out of Git.

## Database and migrations

`DATABASE_URL=sqlite:///./storage/footlytics.db` resolves against the repository
root. The default storage directory is already present; create a parent directory
yourself if choosing a different database location. From the root:

```bash
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current
python -m alembic -c backend/alembic.ini check
```

From `backend/`, the equivalent is `python -m alembic upgrade head` using its
virtual environment. Revision `0001_users_and_roles` creates:

- `users`: ID, normalized unique email, full name, password hash, active flag and
  creation/update timestamps.
- `roles`: unique stable internal name and display name.
- `user_roles`: composite primary key and foreign keys for multiple roles.

The migration inserts the five canonical roles once. Repeating `upgrade head`
does not duplicate them. `ensure_roles()` can safely restore missing role seeds
and is also used by the administrator command. API startup never creates tables.
Use reviewed Alembic revisions for schema changes; downgrades can destroy data.

SQLAlchemy sessions are request-scoped and closed after each request. SQLite
enforces foreign keys and uses Python 3.12's explicit transaction handling with
`check_same_thread=False`. Schema types avoid SQLite-specific enums. PostgreSQL
will need its driver and a tested connection URL; it has not been exercised yet.
Timestamps are UTC: SQLite stores UTC values and the ORM restores their timezone;
API timestamps include `Z`. Account edits, including role changes, update
`updated_at` through the service layer.

## Create the first administrator

After applying migrations:

```bash
python scripts/create_admin.py --email admin@example.com --name "FOOTLYTICS Admin"
```

Use your intended email/name. The script securely prompts twice for an 8–128
character password, hashes it and grants the admin role. For non-interactive
automation, supply `FOOTLYTICS_ADMIN_PASSWORD` in the process environment and
remove it from the parent environment afterwards; there is no password CLI flag.
Without that variable a real interactive terminal is required.

Repeating the command for an existing active admin succeeds without changing the
account or password. An existing non-admin/inactive account causes a clear error;
the script never silently promotes, reactivates or resets existing accounts.

## Signup and administrator approval

New users choose **Sign up** on the login page, or open `/signup`, and submit
full name, email, password and one **Requested role**: Coach, Analyst, Player
or Club Management. Signup creates a pending access request, not a login account. Pending and rejected applicants cannot sign in.

An existing administrator opens **Access requests** (`/admin/signup-requests`),
reviews the applicant and requested role, optionally assigns an active club,
then chooses **Approve access** or **Reject request**. Approval grants exactly the
requested non-admin role and uses the applicant's chosen password. Older requests
without a role require an explicit single non-admin choice. Approved/rejected requests remain
in the review history. Existing administrator-created accounts are unchanged.

A non-admin approved without a club can sign in but has no club records until a
membership is assigned under Clubs. Player access additionally needs a linked
active Player profile and squad membership. A requested role grants no access
until approval. Applicants cannot select Admin or grant themselves club access.

The public API is `POST /api/auth/signup` (202, generic receipt, no token);
`requested_role` is required and Admin is rejected. Approval rejects a different
role or multiple roles.
Admin-only routes are `GET /api/signup-requests?status=pending` (also `approved`
or `rejected`), `POST /api/signup-requests/{id}/approve` with `roles` and optional
`club_id`, and `POST /api/signup-requests/{id}/reject`. Passwords are hashed and
never returned; the request's hash is cleared after review. Duplicate submissions
do not overwrite accounts or requests, and concurrent reviews accept only one
decision. Run `python -m alembic -c backend/alembic.ini upgrade head` before
starting the updated API/worker. Migration `0014_signup_requested_role` preserves
legacy requests; `0015_team_color_prototypes` adds versioned team-color evidence.
Restart already-running API/worker processes after code or migration changes.
An older API rejects `requested_role` as an unexpected field.

There is no email verification or notification service. Administrators verify
applicants and communicate approval manually. Rejected applicants should contact
an administrator; submitting again does not reopen a reviewed request.

## Post-core hardening and team-color setup

Hardening implementation and documentation are finalized. The initial backend
full run recorded **1,177 passed / 7 failed**; the shared migration 0015 downgrade
issue was fixed, with **92 coordinate/report tests** and **3 remaining affected
migration tests** passing in post-fix verification. The complete backend suite was
not rerun after that fix. Frontend **175 passed**; browser **77 checks passed**.
See [the exact verification record and limitations](docs/HARDENING.md#final-verification).

Preparation now reuses a successful job for the unchanged active video; queued or
running duplicates are rejected. Match Details shows **Video Prepared ✓** and
keeps older terminal jobs under **Processing History**. Replacing the video allows
new preparation; failed attempts use the existing retry action.

For **Match Analytics → Team Assignments → Set Team Colors**, use the tracking
review to identify a Track ID and processed frame for a clear torso. Preview it,
add examples to Team A and Team B (up to ten total), then **Save prototypes** and
**Re-run classification**. A coach/analyst with club access or an admin may edit;
Club Management is read-only. The worker uses existing tracks and real selected
video crops; it does not rerun YOLO. Changing tracking invalidates saved examples.
Classification records automatic/user-seeded mode and sample provenance. Manual
per-track overrides take precedence. Weak or conflicting evidence remains Unknown.

Player details and heatmaps now show observed/video duration, coverage, and short
fragment/low-coverage warnings. These describe visible usable intervals, not full
player identity or match coverage. See [hardening results and reproduction](docs/HARDENING.md)
for the 60-second cached comparison and rejected stitching experiment. The frozen
Phase 15 evaluation is unchanged. Architecture and CV dependencies are available
as separate [system](docs/architecture.svg) and [pipeline](docs/cv-pipeline.svg) SVGs.

## Authentication and authorization

Login accepts JSON, not an OAuth2 form:

```http
POST /api/auth/login
Content-Type: application/json

{"email":"admin@example.com","password":"<your password>"}
```

The response contains `access_token` and `token_type: "bearer"`. Send the token
as `Authorization: Bearer <access_token>`. In `/docs`, obtain a token using login
and paste it into the bearer **Authorize** dialog.

The JWT contains the database user ID as `sub`, issuance time, expiration and
access-token type. Verification pins the configured algorithm, validates required
claims and loads the user and roles from the database on every protected request.
Inactive accounts fail login and existing-token authentication. Role changes take
effect on the next request; roles in a browser are never an authorization source.

Passwords use Argon2id through pwdlib, following the
[FastAPI security guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
Creation requires 8–128 characters without composition rules. Emails are validated
and normalized to lowercase, including the local part, for account uniqueness.
Passwords/hashes are absent from user responses; validation errors omit submitted
input values. Failed logins use a uniform 401 response, and unknown accounts still
perform password-hash verification. Successful API responses are marked no-store.

| Internal role | Current permissions |
| --- | --- |
| `admin` | All users and all clubs, assignments, rosters and matches; no club assignment required |
| `coach` | Read assigned active clubs; create/edit teams, players, squads and matches there |
| `analyst` | Read assigned active clubs and rosters; create/edit/archive matches there |
| `player` | Read own linked active player profile, current active teams and relevant matches in an assigned active club; no writes |
| `club_management` | Read assigned active clubs, teams, players, squads and matches; no domain writes |

Users may have several roles. `require_roles(...)` grants access when any listed
role matches; admin is not an implicit bypass unless listed. Global roles determine
capabilities; `ClubMembership` determines where non-admin users can use them.
Roles combine additively: a Coach+Player account has Coach access in assigned clubs.
Admins cannot deactivate themselves or remove their own admin role through PATCH.
This protects ordinary administration from accidental self-lockout.

| Endpoint | Access / behavior |
| --- | --- |
| `GET /api/health` | Public liveness |
| `POST /api/auth/login` | JSON credentials; returns bearer token |
| `GET /api/auth/me` | Active authenticated user; own profile and roles |
| `GET /api/users?offset=0&limit=25` | Admin; `items`, `total`, `offset`, `limit` (limit 1–100) |
| `POST /api/users` | Admin; email, full_name, password, nonempty roles; returns 201 |
| `GET /api/users/{id}` | Admin; user details |
| `PATCH /api/users/{id}` | Admin; email, full_name, is_active and/or nonempty roles |

PATCH accepts omitted unchanged fields, not explicit nulls or an empty object.
Password/hash fields are rejected. Deactivation uses `is_active=false`; there is
no permanent-delete endpoint. Errors use FastAPI's `detail` envelope: 401 for
missing/invalid/expired/inactive credentials, 403 for insufficient roles, 404 for
missing users, 409 for duplicate email/self-lockout, and 422 for invalid input.

## Frontend sessions

The auth provider verifies `/auth/me` before rendering protected pages. The shared
API client attaches bearer tokens, clears the session on authenticated 401s, and
keeps it for 403 or temporary server/network failures. A stale 401 from a previous
session cannot clear a newer token. Logout clears the token and query cache.

Tokens are held in memory and centralized **sessionStorage**: a page reload can
restore the session, and storage is scoped to the browser tab/session. If browser
storage is blocked, the app falls back to memory and reports that in the console.
JavaScript can access this storage, so XSS can expose a token; do not insert
untrusted HTML. Use HTTPS outside local development. There are no refresh tokens,
MFA, password-reset/change flow, login throttling or server-side token blacklist.
These are deployment limitations, not implemented protections.

Logout is browser-side only. An issued JWT can still be used until expiry unless
the user is deactivated or the signing secret is rotated. There is deliberately
no backend logout endpoint claiming revocation. Browser role checks hide/deny UI;
the backend independently enforces role and club scope for every domain route.

## Frontend user interface

The React frontend follows the "Matchday Control Room" design system recorded in
[docs/UI_REDESIGN.md](docs/UI_REDESIGN.md): dark surfaces, restrained green
accents, Lucide icons and shared components. The redesign changes presentation
only; routes, API contracts, permissions and calculations are as described here.

**Navigation.** A role-aware sidebar groups *Workspace* (Home, Matches), *Squad
data* (Clubs, Teams, Players) and *Administration* (User management, Access
requests; Admin only). It becomes an icon rail on tablets and a drawer on phones.
The top bar shows breadcrumbs that name the open match from data already loaded.

| Screen | What it shows |
| --- | --- |
| Home | Record totals, latest matches with their genuine latest job state and role-aware quick actions. |
| Matches / Match details | Filtered match rows; a match header (teams, format, date, pitch size, video status) and the **processing pipeline**, derived only from the current video's jobs and current-result checks: Not started, Queued, Running, Completed, Completed with warnings, Failed, Cancelled or Needs regeneration, with the next safe step and the existing Run/Retry actions. |
| Pitch calibration | A step guide; frame and pitch panels with numbered matching landmarks (frame circles, pitch squares) and X/Y orientation; the saved reprojection error, pair count and homography matrix from the backend. |
| Detection & tracking review | YOLO and ByteTrack saved-frame viewers with processed-frame navigation (buttons, scrubber, typed frame, ←/→, PgUp/PgDn, Home/End), full-resolution inspection, job status and retry. |
| Match analytics | Overview (KPIs, result availability, at a glance), Players (metrics table and track details), Team Tactics (data basis, team comparison, metric lists, time series and team centroid paths), Heatmap, Team Assignments, analytics processing and Reports/Exports. |
| Access and squad data | Sign-in/sign-up, access requests, users, clubs, teams, players and squads. |

Opening a page never starts processing. Missing, stale or replaced results are
shown as such, never as zero. Saved-frame previews are fetched with the session
token, validated (video, job, timestamp, frame, JPEG and dimensions), and their
object URLs released when replaced. The Analytics route is loaded on demand and
framework code is a separately cached chunk.

## Football domain and access

Revision `0002_clubs_teams_players_matches` adds six tables without changing
existing users, password hashes, roles or assignments:

- `clubs`: normalized case-insensitive unique name, optional short name and
  description, active status and timestamps.
- `club_memberships`: unique `(club_id, user_id)` access assignments. Admins
  assign existing active users; this is not a second role system.
- `teams`: club-owned squads, names unique within a club, optional description
  and short name, active status. Different clubs can reuse team names.
- `players`: club-owned footballers with first/last/display name, optional birth
  date and position, active status and optional unique `user_id`.
- `squad_memberships`: player/team association with optional shirt number (1–99),
  active status and joined/left dates. A player can belong to several teams in
  their club. Removing a player ends the association; adding them again creates
  a new row and preserves history.
- `matches`: club, title, Team A/B, format, UTC date/time, actual pitch length and
  width in metres, venue, notes, creator, archive flag and timestamps.

**User is not Player.** A football profile needs no login. Linking a login account
is optional, one account per player and one player per account; it requires an
active account assigned to the same club. Linking grants no roles or club access.
Removing the assignment or disabling the profile revokes Player access on the
next request. Players see only their own squad row, not teammates' profiles.
Their match access follows their current active team memberships; historical
match participation is not yet modeled. Staff retain access to inactive records
within active clubs for history. Inactive clubs are visible only to admins and
must be reactivated before editing child records.

The shared `auth/club_access.py` helpers scope both list/count queries and detail
lookups. Unassigned/inaccessible IDs return 404, insufficient global roles return
403, and invalid credentials return 401. Filters, nested squad IDs and submitted
relationships cannot bypass these checks. Membership removal takes effect for
already-issued tokens; the API reloads assignments on each request. Safe nested
account references contain only ID and full name.

Team and player club ownership is immutable in this phase; match club and creator
are also immutable. Clubs, teams and players deactivate, matches archive, and
squad removal is soft. There are no hard-delete endpoints for those records.
Removing a club access assignment deletes only that access association.
Foreign keys use RESTRICT for domain history. Composite foreign keys enforce
same-club squad and match relationships at database level. Partial unique indexes
(declared for SQLite and PostgreSQL) prevent duplicate active squad membership
and active shirt-number conflicts within a team. Null shirt numbers are allowed.

Match teams must be distinct and belong to the match club. New selections must be
active. Formats are exactly `11v11` or `5v5`. Pitch X means **length**, Y means
**width**, in metres, stored on each match. The UI suggests 105 × 68 m or 40 × 20 m
when changing format; these are editable starting values, not measured data or
competition regulations. Broad input bounds are length 10–150 m, width 5–100 m,
with length ≥ width, rejecting non-finite values. These bounds catch implausible
input without forcing every pitch into one standard. Enter the actual dimensions.
The API requires timezone-aware match and squad timestamps, normalizes to UTC,
and returns `Z`; the browser accepts/displays local time. Future birth dates are
rejected. Patches validate the resulting match, including unchanged fields.

## Football API and screens

All paths below have the `/api` prefix and require authentication. List responses
use `items`, `total`, `offset`, `limit`; default 25, maximum 100. Totals count only
accessible records. POST returns 201, PATCH returns the updated record, DELETE
returns 204. Invalid input is 422 and uniqueness conflicts are 409.

| Endpoints | Behavior / filters |
| --- | --- |
| `GET/POST /clubs`; `GET/PATCH /clubs/{id}` | Scoped read; admin writes; `active` filter |
| `GET/POST /clubs/{id}/members`; `DELETE /clubs/{id}/members/{user_id}` | Admin manages access assignments |
| `GET /clubs/{id}/player-account-options` | Admin/Coach picker of eligible unlinked club accounts, ID/name only |
| `GET/POST /teams`; `GET/PATCH /teams/{id}` | Scoped read; Admin/Coach writes; `club_id`, `active` |
| `GET/POST /players`; `GET/PATCH /players/{id}` | Scoped read; Admin/Coach writes; `club_id`, `team_id`, `active` |
| `GET /players/{id}/squads` | Scoped current/history membership list |
| `GET/POST /teams/{id}/squad` | Scoped read; Admin/Coach adds; `active` |
| `PATCH/DELETE /teams/{id}/squad/{membership_id}` | Admin/Coach updates shirt/timing or ends membership |
| `GET/POST /matches`; `GET/PATCH /matches/{id}` | Scoped read; Admin/Coach/Analyst writes; `club_id`, `team_id`, `match_format`, `archived` |

The frontend provides `/clubs`, `/teams`, `/players`, `/matches` and their `/:id`
detail pages. Create/edit forms appear within management pages; `/matches/new`
is role-protected. Club details include admin membership assignment. Team details
include current squad/history, shirt edits and removal. Player details include
optional account linking and squad history. Match details include editable metadata,
archive/restore and an honest unavailable video-analysis section. Forms show
validation/API failures and disable duplicate submissions. Lists have filters,
pagination and useful empty states. Selectors fetch all available pages.

To use the workflow, create real Coach/Club Management accounts in **User
management**, create a club in **Clubs**, and assign those accounts under **Club
members**. Sign in as the Coach, create two teams and football players, assign
players under a team's **Squad**, then create a match. Select the club, its two
teams, format, local time and actual pitch dimensions. Club Management can view
the assigned data but cannot change it. No demonstration accounts, clubs, players
or matches are seeded in the development database.

The Home page obtains four counts from the scoped APIs. Loading and failures
remain explicit; counts include inactive/archived accessible records. They are
management totals, not analytics.

## Match videos, storage and preparation

Revision `0003_match_videos_processing_jobs` adds two tables without changing
earlier migrations or existing football/authentication data:

- `match_videos` (`MatchVideo`): match ownership, display/generated names, relative
  storage path, byte size, MIME type, metadata, uploader, SHA-256, warning, active
  flag and UTC timestamps. A partial unique index allows one active source per
  match. Retired records and files preserve earlier job history.
- `processing_jobs` (`ProcessingJob`): match and source video, controlled job
  type/status, progress/stage, creator, RQ identifier, start/finish timestamps,
  safe errors/warnings and retry count. An internal attempt number prevents stale
  deliveries from changing a retried job. Foreign keys require the video to belong
  to the same match; checks constrain progress to 0–100 and status/type values.
  A partial unique index prevents duplicate active jobs for a source/type.

Admin can manage videos/jobs globally; Coach and Analyst can manage them for
accessible matches in active clubs. Club Management is read-only. Player video
reads follow existing match access; job endpoints return 403 and the job UI is
hidden. Archived matches keep readable history but reject uploads and job changes.
Every metadata/file/job route reuses backend match and club authorization.

| Endpoint | Behavior |
| --- | --- |
| `POST /api/matches/{id}/video` | Multipart field `file`; new upload, 201; existing source returns 409 |
| `PUT /api/matches/{id}/video` | Explicit replacement, 200; missing source returns 404 |
| `GET /api/matches/{id}/video` | Metadata, or JSON null if no source; never file bytes or storage paths |
| `GET /api/matches/{id}/video/file` | Protected active file; supports byte ranges (206), no public mount |
| `POST /api/matches/{id}/jobs/video-preparation` | Persist and enqueue; 202 with job record, without waiting for execution |
| `GET /api/matches/{id}/jobs?offset=0&limit=25` | Scoped paginated history; active jobs first, then newest created |
| `GET /api/jobs/{id}` | Scoped job status, progress, timestamps and safe messages |
| `POST /api/jobs/{id}/retry` | Retry failed/cancelled job for the active source; 202 |

MP4 and MOV are supported when the installed decoder can read their codec.
Authorization and match checks happen before multipart parsing. The parser accepts
one file, bounds headers and counts actual bytes, including requests without a
Content-Length. Starlette spools larger parts to disk; the upload service copies
in 1 MiB chunks to `raw/matches/<id>/.temporary/`, hashing SHA-256 during that copy.
It never reads an entire match into memory. Allow disk capacity for both temporary
copies during upload, the final video, and retained history.

Extension/MIME checks are followed by ffprobe metadata and an actual OpenCV frame
decode in separate time-limited subprocesses, with no shell interpolation. The
decoders permit local MP4/MOV containers, not network playlists. Dimensions, finite
positive duration and plausible FPS are checked; limits currently cap 240 FPS,
24-hour duration and approximately 8K frame area. No calibration or player analysis
runs during upload. OpenCV fallback requires enough metadata to calculate duration.

Successful files receive a generated UUID name, for example
`storage/raw/matches/12/<uuid>.mp4`. The database stores only the path relative to
`STORAGE_DIR`. Original filenames are display-only; traversal, absolute paths,
redirecting symlinks/junctions and filename collisions cannot redirect publication.
The storage service reserves the unique name and atomically moves the validated
file on the same filesystem. No unprotected storage directory is mounted.

**Replace Video** is an explicit action. A bad, duplicate or oversized replacement
keeps the old source active and removes temporary output. A short match-row write
transaction rechecks account/club access, the expected source ID and active jobs
after validation; simultaneous replacements can publish only one new source.
Queued/running processing blocks replacement. Old files remain protected history
and have no historical-file download route. Future calibration/results must be
bound to `video_id` and invalidated when a different source becomes active.

The real `video_preparation` worker checks that the active source still exists and
its size is unchanged, reopens it, decodes a frame and refreshes metadata. Progress
is a sequence of completed preparation milestones, not a percentage of analyzed
match frames: queued 0, claimed 10, source verified 25, metadata/frame verified 80,
saved 100. Status is one of `queued`, `running`, `completed`,
`completed_with_warnings`, `failed` or `cancelled`. Fallback metadata finishes with
warnings; it never invents codec/container information or analytics.

The API commits the job before enqueueing serializable job/attempt identifiers.
Failure to submit returns 503 and persists a safe failed state for retry. It never
executes work synchronously as a fallback. A worker that already claimed an attempt
is not overwritten by a lost enqueue acknowledgement. Retries clear transient
fields, increment retry count/attempt and use a new unique RQ ID. Duplicate/stale
deliveries cannot claim the job. Normal worker errors and RQ timeout/workhorse
failure callbacks persist safe messages; detailed exceptions go to process logs.

Match details display selected filename/size, upload/validation activity, actual
metadata, explicit replacement feedback and preparation jobs. Upload progress is
an indeterminate busy state because the fetch client does not report transmitted
bytes. **Prepare Video** and **Retry** call the real APIs. TanStack Query polls
queued/running jobs every two seconds and stops for terminal states or failed
refreshes; the active page remains monitored while browsing older job pages.
The file endpoint is available for later review; no browser video player is added.

For a manual check, sign in as an assigned Coach, open a match, upload a small
readable MP4/MOV and check its real metadata. Try a corrupt replacement and confirm
the source remains unchanged. With Redis and the separate worker running, click
**Prepare Video** and watch the job finish. With Redis stopped, it should show a
safe failure and an available retry after service restoration. Never use real
full-match footage in ordinary tests.

Preparation verifies the first decoded frame, not every frame or full-file
integrity; the worker's size check is not a second SHA-256 scan. Frame-count/FPS
duration can be approximate, especially for variable-frame-rate footage. Codec
support depends on the runtime. Cancellation, resume/chunked client uploads,
automatic retention cleanup and crash reconciliation are not implemented. A hard
process/power failure between filesystem/DB publication or DB/Redis submission
can leave an orphan file or stale job; reconcile these during maintenance after
confirming no upload/worker is active. Back up both SQLite and storage together.
Keep the worker running to consume accepted queued jobs.

## Pitch calibration — Phase 5

**Phase 5A — complete. Phase 5B — complete.** Calibration maps image pixels onto
the pitch plane with a homography. Pitch coordinates are metres: X is length and
Y is width, using the Match's own dimensions. Supply 4–64 ordered correspondences
as `{ "x": number, "y": number }`; `image_points[i]` matches `pitch_points[i]`.
Counts must match, and duplicate, degenerate, non-finite or out-of-bounds points
are rejected. Image points use the returned frame's original pixel dimensions,
with origin at the upper left and bounds `0..width-1`, `0..height-1`.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/matches/{id}/calibration/frame?timestamp_seconds=0` | Seek and decode one real JPEG; timestamp must be finite, nonnegative and less than video duration |
| `GET /api/matches/{id}/calibration` | Current calibration, or JSON null when absent/stale |
| `POST /api/matches/{id}/calibration` | Create the current video's first calibration; 201 |
| `PUT /api/matches/{id}/calibration` | Replace an existing calibration for the current video; 200 |

POST/PUT require `video_id`, `image_points` and `pitch_points`, with optional
`source_timestamp_seconds` (default 0). The JPEG response exposes `X-Video-Id`,
`X-Frame-Number`, `X-Frame-Timestamp-Seconds`, `X-Frame-Width` and `X-Frame-Height`
headers used by the calibration frontend. Frame numbers are zero-based; timestamps/positions are those
reported by OpenCV after seeking, so codec and variable-frame-rate seeking can
affect precision. No full-video scan or persistent image artifact is generated.

Migration `0004_pitch_calibration` stores `PitchCalibration`, JSON landmarks and
matrix, source frame/dimensions, creator and UTC timestamps. There is one row per
match/video. Replaced-video calibrations remain stored but are never returned as
current. Changing Match pitch dimensions also hides the stale calibration; use
PUT to recalibrate that video. Saves verify that the submitted video is still active.
Admin, Coach and Analyst may modify accessible calibration; Club Management and
Player reads follow existing Match scope, with no modification permission.

The independent `cv/homography.py` uses `cv2.findHomography`, RANSAC for more than
four pairs (0.5 m inlier threshold), and one `cv2.perspectiveTransform` call per
batch. `reprojection_error` is the mean Euclidean residual **in metres over all
supplied pairs**, including RANSAC outliers. A small fitting residual is not an
independent accuracy measurement. Calibration assumes a planar pitch and unchanged
camera pose; pan, zoom or cuts require recalibration. Camera-motion detection is
pending. See the [OpenCV homography documentation](https://docs.opencv.org/4.x/d1/de0/tutorial_py_feature_homography.html).

From Match Details, choose **Calibrate Pitch** after uploading a video to open
`/matches/:matchId/calibration`. The saved frame or timestamp 0 loads through the
authenticated API. Enter a timestamp and choose **Load Frame** to select another;
this clears draft points while preserving the saved calibration. Click an image
landmark, then its matching location on the SVG pitch, and repeat for 4–64 pairs.
Both surfaces show the same point numbers; remove the last point or reset as needed.
Image clicks use the decoded frame's original pixels. Pitch clicks use Match
metres, from top-left `(0, 0)` to bottom-right `(length, width)`. Interior pitch
markings are schematic, especially for 5v5; use known, measured landmarks.

**Save Calibration** creates a calibration; **Update Calibration** explicitly
replaces an existing one. Backend validation messages remain visible with the
draft points. Quality displays the backend's **Mean reprojection error: X.XX m**,
with unsaved changes clearly distinguished. Club Management, Players, archived
matches and inactive clubs have a read-only view. The panels stack on small screens;
landmark selection is intended for desktop/tablet use. No frontend homography or
competing error calculation is performed.

## Player detection — Phase 6A

`POST /api/matches/{match_id}/jobs/player-detection` returns a queued job with HTTP
202. Admin, Coach and Analyst can start detection within existing resource access
rules; Club Management and Player cannot. An active video and current calibration
are required. The existing Redis/RQ worker receives only job/attempt IDs, streams
frames incrementally and persists progress, safe failures and a detection summary
through the existing job endpoints. Inference never runs in an HTTP request.

The default `yolo11n.pt` downloads on first worker use into ignored
`storage/models/`; configure a local `.pt` path for offline operation. Settings
control confidence, inference size, device and frame stride. Retained `person`
boxes are candidates, not confirmed football players. Boxes remain in original
image pixels. ROI filtering tests each box's bottom centre only when calibration
explicitly supplies a valid polygon from all four pitch corners; incomplete
corner information skips filtering with a warning. This assumes a fixed camera;
disable ROI for moving-camera footage.

Rows stream to an attempt-specific CSV under protected `storage/tracks/`, outside
SQLite. Only a successful, still-current attempt records the artifact reference;
failed attempts clean up their output. Source-video and calibration versions are
rechecked before completion. Responses expose summary metadata, not filesystem
paths. Timestamps use decoder positions, with an explicitly reported nominal-FPS
fallback. Detection review is described below; coordinates remain in image pixels.

## Player tracking — Phase 7A

`POST /api/matches/{match_id}/jobs/player-tracking` queues a `player_tracking`
job (HTTP 202) for an authorized Admin, Coach or Analyst. It requires the active
video, current calibration and a completed, current detection CSV. Missing,
invalid or stale detections return 409; tracking never reruns YOLO. Club Management
is read-only and Player cannot start jobs. The existing job/retry endpoints expose
progress, safe errors and `tracking_summary`, without filesystem paths.

`BaseTracker` / `ByteTrackTracker` stream detections grouped by sampled frame into
[Ultralytics ByteTrack](https://docs.ultralytics.com/reference/trackers/byte_tracker/).
The recorded frame count and stride restore empty updates without decoding video.
CSV columns are `frame_number,timestamp_seconds,track_id,x1,y1,x2,y2,confidence`;
boxes remain in image pixels and timestamps come from the source detections.
Confirmed observations are written, with no invented rows across detection gaps.
IDs belong to one match and tracking attempt, not a known player or another match.

Output uses protected `storage/tracks/matches/<match_id>/videos/<video_id>/jobs/`
`<job_id>/attempt-<attempt>-<uuid>.csv`. A successful attempt publishes its reference
only after rechecking video, calibration and detection versions; failed attempts
clean up. Progress counts processed sampled frames, including empty ones.

Settings default to `TRACK_HIGH_THRESH=0.25`, `TRACK_LOW_THRESH=0.1`,
`TRACK_MATCH_THRESH=0.8`, `TRACK_BUFFER=30`. The buffer counts source frames: at
stride N ByteTrack's buffer is `TRACK_BUFFER // N` sampled updates (at least one),
so lost tracks span about the same time and stride 1 is unchanged. Detection also
stores boxes from `TRACK_LOW_THRESH` up to `YOLO_CONFIDENCE` as ByteTrack-only
candidates, excluded from detection counts and overlays, so the low-score association
can keep IDs through partial occlusion. `TRACK_HIGH_THRESH` must be at least
`YOLO_CONFIDENCE`, so tracks start only from reported detections. Detection results
saved before this change lack the candidates; tracking them completes with a warning.
Long occlusions, camera motion and crowded crossings can split tracks or switch IDs.
There is no identity recognition or gap interpolation. Phase 9 maps saved tracking
boxes to pitch coordinates separately.

Run tracking/tests in the existing WSL CPU environment. `lap>=0.5.12,<0.6` is now
in the backend requirements (locked at 0.5.13). The verified runtime retained
Ultralytics 8.4.170 and CPU PyTorch 2.14.1; no model inference is needed for tracking.

## Detection and tracking review

Open **Player Detection & Tracking Review** from Match Details
(`/matches/:matchId/review`). Inspect YOLO person boxes/confidence and ByteTrack
IDs on selected processed frames, alongside job status, counts and sampling bounds.
Admin, Coach and Analyst can start existing detection/tracking jobs; Club Management
can review results read-only. Players have no internal CV review access.

Protected endpoints:

- `GET /api/matches/{match_id}/detections/summary`
- `GET /api/matches/{match_id}/detections/preview?frame_number=...`
- `GET /api/matches/{match_id}/tracking/summary`
- `GET /api/matches/{match_id}/tracking/preview?frame_number=...`

Previews seek one frame using the existing isolated decoder and draw saved CSV
observations; they never rerun YOLO or ByteTrack. Omitting `frame_number` selects
the first observed frame, or frame zero for an empty result. Only sampled frames
are accepted. Current source/calibration/artifact guards reject stale results,
and the browser binds requests to the displayed job version. Empty states show
missing results without fabricated counts. Tracking averages include empty sampled
frames; `first_frame`/`last_frame` describe the processed range. CSV lookup streams
up to the selected frame with a timeout; no full annotated video is generated.

## Team jersey classification — Phase 8

The backend reads the current tracking CSV and seeks selected source frames using
the existing bounded decoder. YOLO and ByteTrack are not rerun. Crops use the
central 20–80% of each box's width and 18–55% of its height, clipped to the image.
Invisible, tiny or malformed crops are skipped. This excludes most head, legs and
box-edge background while retaining green jerseys. Only one decoded frame and
capped compact color samples per track are held in memory.

Each crop yields a median [CIE Lab color](https://docs.opencv.org/4.x/de/d25/imgproc_color_conversions.html)
and the fraction of pixels within 25 Lab units of it. At least three valid frames
contribute to a track median; variation between frames reduces evidence quality.
Deterministic two-cluster Lloyd K-Means uses sorted colors and fixed farthest-color
initialization. Fewer than two usable tracks or centroid separation below 20 Lab
units produces Unknown. Confidence combines crop consistency, temporal consistency,
centroid separation, nearest-cluster margin and absolute color proximity. This
bounded heuristic quality score is not a calibrated probability; low scores remain
Unknown. Thresholds describe the implemented heuristic, not measured match accuracy.

Team records currently have no configured jersey colors. Centroids are ordered by
ascending `(L, a, b)`: first is `team_a`, second is `team_b`. The same evidence maps
consistently across runs. These color groups need human confirmation against the
actual Match teams; track IDs remain local to one tracking result.

| Setting | Default | Meaning |
| --- | --- | --- |
| `TEAM_SAMPLE_INTERVAL` | 15 | Minimum source-frame gap between attempts per track |
| `TEAM_MAX_SAMPLES_PER_TRACK` | 20 | Maximum crop attempts per track, including rejected crops |
| `TEAM_MIN_SAMPLES` | 3 | Minimum valid frame samples; must be at least two |
| `TEAM_MIN_CROP_WIDTH` / `TEAM_MIN_CROP_HEIGHT` | 8 / 8 | Minimum cropped dimensions in pixels |
| `TEAM_UNKNOWN_THRESHOLD` | 0.6 | Minimum automatic assignment quality |

- `POST /api/matches/{match_id}/jobs/team-classification` queues the existing RQ
  pipeline and returns 202. Current video, calibration, detections and tracking
  must pass the shared version guards; missing/stale inputs return 409.
- `GET /api/matches/{match_id}/team-assignments` returns paginated current track
  assignments, automatic confidence, manual/effective team and correction author.
- `PATCH /api/matches/{match_id}/tracks/{track_id}/team` accepts a `team` value of
  `team_a`, `team_b` or `unknown`, for example `{"team":"team_a"}`;
  `{"team":null}` clears an override.
  Run classification before correcting a track. Manual corrections survive
  reclassification of the same tracking result and take precedence over automation.

Admin has global access; Coach/Analyst operate within assigned clubs. Club Management
can read, Player has no internal classification access, and anonymous requests are
denied. Responses expose no storage paths. Workers receive only job ID and attempt,
report actual processed-frame progress, and publish assignments and completion in
one transaction after input/attempt revalidation. Failures preserve prior valid
assignments. Migration `0007_team_classification` stores one assignment per match,
tracking version and track ID, with nullable overrides; historical versions remain
hidden when upstream inputs change. Job summary counts describe automatic results.

Similar or striped kits, lighting changes, occlusion and ID switches can produce
Unknown or incorrect groups; this method does not identify referees, goalkeepers
or named players. Sampling covers the first bounded set of eligible track frames.
Repeated isolated frame seeks favor bounded memory over throughput. Real-match
accuracy, live Redis delivery and PostgreSQL remain unverified. Phase 13 provides
the team-correction frontend. No new dependencies were needed for Phase 8.

## Pitch coordinate conversion — Phase 9

The backend streams the current tracking CSV in batches of at most 256 rows and
uses the saved calibration through Phase 5 `homography.transform_points()` and
`cv2.perspectiveTransform()`. It does not refit homography, decode video, rerun YOLO
or ByteTrack, or depend on team classification. Team corrections do not invalidate
coordinate results.

Each valid box uses the bottom-centre ground point:
`pixel_x = (x1 + x2) / 2`, `pixel_y = y2`. This approximates contact with the pitch;
the box centre lies above the ground plane. Coordinates are **metres**, with
**X = pitch length** and **Y = pitch width**, using the Match's
`pitch_length_metres` and `pitch_width_metres`. Off-pitch coordinates remain
unchanged and receive `inside_pitch=false`; bounds allow only `1e-6` metres of
floating-point tolerance. No clipping, smoothing or interpolation is applied.

Boxes with non-finite, nonnumeric, reversed or zero-area coordinates are skipped
and counted in `skipped_invalid_boxes`, without changing valid rows. Invalid CSV
metadata/order/counts or malformed/non-finite transform output fail the job and
prevent publication. An empty result has a header-only CSV and a warning.

Each attempt writes a protected artifact under
`storage/tracks/matches/<match_id>/videos/<video_id>/jobs/<job_id>/attempt-<attempt>-<uuid>.csv`.
Valid rows retain `frame_number,timestamp_seconds,track_id,x1,y1,x2,y2,confidence`
and add `pixel_x,pixel_y,pitch_x,pitch_y,inside_pitch` (`true`/`false`). The source
tracking CSV is unchanged. SQLite holds provenance and a small summary, not rows.
Temporary output becomes current only after processing and final input/attempt
checks succeed. Failed attempts preserve previous valid results and remove their
own partial output; changed video, calibration or tracking inputs make results stale.

- `POST /api/matches/{match_id}/jobs/coordinate-mapping` returns 202 with a job ID.
  Current video, calibration and tracking must pass the shared version guards.
- `GET /api/matches/{match_id}/coordinates/summary` returns total/mapped/skipped
  rows, inside/outside counts, unique mapped tracks, first/last mapped frame and
  source metadata. Missing or stale inputs/results return 409.

Admin has global access; Coach/Analyst can run/read within assigned clubs. Club
Management is read-only; Player and anonymous access are denied. Responses expose
no filesystem paths. Workers receive job ID and attempt only, and progress measures
processed input rows through loading, mapping, saving and completion stages.

These are raw planar-pitch estimates. Calibration error, camera movement, cuts,
occluded feet and inaccurate boxes affect positions; camera motion is not corrected
automatically. Real-match positional accuracy remains unmeasured. Raw coordinates
feed the Phase 10 cleaner below; player analytics consume its usable cleaned output.

## Trajectory cleaning — Phase 10

Tracked ground points can jitter, jump or disappear temporarily. The backend cleans
the current Phase 9 coordinate CSV without modifying it or rerunning upstream CV.
Every source observation remains in a separate output, including rejected points.
Tracks are independent and ordered by timestamp, then frame and original row number.
External sorting uses 4,096-row chunks and merges at most 16 runs at once; bounded
per-track windows avoid loading the match into RAM. Attempt-owned temporary files
are removed on completion or failure.

Outside-pitch rows retain their raw coordinates, have `usable=false`, null clean
positions and status `outside_pitch`; coordinates are never clamped. After sorting,
negative timestamps, duplicate/non-increasing times and conflicting frame order
are retained as unusable observations. Exact ties use original row order. Temporal
conflicts do not produce zero-time divisions or invented positions.

An isolated teleport is rejected when both adjacent steps exceed the configured
quality limit, but the surrounding reliable points agree over an allowed continuity
gap. The rejected point never becomes the reference for later observations.
Persistent or ambiguous spatial jumps instead start a new segment, as do gaps
longer than the configured limit between usable observations. Segment IDs restart
at one within each track; later analytics must not connect different segments.
The distance/time comparison is a quality check, not a reported player metric.

Smoothing uses a short window within each uninterrupted usable run. It forms a
timestamp-linear baseline through the window endpoints, takes the median residual
per axis, and moves the centre observation halfway toward that local estimate.
Each adjustment is capped in metres. This preserves constant motion at irregular
timestamps; run endpoints remain unchanged. Rejected points, long gaps and segment
boundaries terminate the window. Proposals that leave the pitch or violate the
neighbor plausibility checks are discarded rather than clamped.

**No interpolation is performed.** Cadence can be irregular, so missing samples
remain gaps, including short gaps. `is_interpolated` is always `false` and
`interpolated_rows` is zero. Smoothing adjusts existing observations only.

| Setting | Default | Meaning |
| --- | --- | --- |
| `TRAJECTORY_MAX_PLAUSIBLE_SPEED_MPS` | 12 | Conservative displacement/time quality limit; configurable heuristic, not an evaluated football maximum |
| `TRAJECTORY_MAX_GAP_SECONDS` | 2 | Maximum continuity gap between usable observations |
| `TRAJECTORY_SMOOTHING_WINDOW` | 3 | Odd observation window from 1–11; 1 disables smoothing |
| `TRAJECTORY_SMOOTHING_MAX_SHIFT_METRES` | 0.5 | Maximum adjustment from a raw position; 0 disables smoothing |

The protected artifact uses
`storage/tracks/matches/<match_id>/videos/<video_id>/jobs/<job_id>/attempt-<attempt>-<uuid>.csv`.
It preserves original frame/time/track, bbox, confidence and pixel fields, adds the
one-based `source_row_number`, and includes `segment_id`, `raw_pitch_x/y`,
`clean_pitch_x/y`, `inside_pitch`, `usable`, `status` and `is_interpolated`.
Rejected clean positions and segment IDs serialize as empty CSV cells: readers
must interpret these as null, never zero. Only metadata and summary enter SQLite.

- `POST /api/matches/{match_id}/jobs/trajectory-cleaning` queues the existing
  ProcessingJob/RQ worker and returns 202 with its job ID.
- `GET /api/matches/{match_id}/trajectories/summary` returns source, usable,
  rejected, outside, jump, temporal-error and smoothed counts, input track count,
  usable segment count, source frame bounds and method/settings provenance.
  `source_rows = usable_rows + rejected_rows`; missing/stale results return 409.

Admin has global run/read access; Coach/Analyst use assigned clubs. Club Management
is read-only, Player has no internal trajectory access, anonymous requests return
401 and cross-club access is denied. No paths or complete CSVs are exposed in JSON.
Workers receive IDs/attempt only and report measured row progress. Final version
checks protect the exact video/calibration/tracking/coordinate chain before
publication; failed retries preserve earlier valid output. Team assignment changes
do not invalidate trajectory cleaning.

ByteTrack ID switches can still create incorrect segments. Homography/calibration
error propagates downstream, and absent true positions cannot be reconstructed.
Smoothing trades some temporal/spatial precision for noise reduction. No cross-track
identity repair is attempted. Real-match cleaning accuracy, live Redis delivery
and PostgreSQL remain unverified. Phase 11 consumes the current usable cleaned rows.

## Phase 11 — Player analytics (backend)

Physical metrics belong to **Match + Track ID**, without automatic roster identity
or cross-track merging. The worker reads only the current valid Phase 10 artifact:
`usable=true` with finite `clean_pitch_x/y`. There is no fallback to raw coordinates,
bounding boxes or Phase 9 positions, and no upstream CV is rerun. Phase 10's
`segment_start` status and defined pitch-boundary tolerance are supported.

A movement interval needs consecutive usable observations of the same track and
segment, increasing timestamps and frames, and the saved cleaning run's continuity
and physical-plausibility limits. **A rejected observation breaks continuity even
when usable observations on both sides share a segment.** Segment boundaries,
non-positive time differences and invalid intervals contribute no movement or time.

- Interval distance is `sqrt(dx² + dy²)` metres between cleaned positions. Total
  distance is the sum of valid interval distances.
- Active duration is the sum of valid interval `dt`, using actual timestamps and
  irregular sampling. It is never the last timestamp minus the first.
- Average speed is total distance / active duration. Maximum speed is the largest
  valid interval distance / `dt`. Both expose m/s and km/h (`m/s × 3.6`). P95 is
  not implemented.
- Empty, rejected-only and single-observation tracks have zero observed distance,
  duration and sprint counts; average and maximum speeds are null when no valid
  interval exists. A valid stationary interval has positive duration and zero
  speed. NaN/Inf are rejected. First/last frame/time describe usable observation
  extents; they are null when no usable observations exist.

| Setting | Default | Meaning |
| --- | --- | --- |
| `PLAYER_SPRINT_SPEED_THRESHOLD_MPS` | 7.0 | Inclusive sprint speed threshold; methodology-dependent |
| `PLAYER_SPRINT_MIN_DURATION_SECONDS` | 1.0 | Minimum summed duration of continuous qualifying intervals |
| `PLAYER_HEATMAP_BINS_X` | 20 | Grid columns along the Match's pitch length |
| `PLAYER_HEATMAP_BINS_Y` | 12 | Grid rows along the Match's pitch width |

A sprint event is a continuous sequence of intervals at or above the threshold
whose total duration reaches the minimum. Low speed, a rejected observation,
invalid time or a segment break ends the candidate. A brief fast burst does not
count as an event. Sprint count, distance and duration reconcile with the persisted
event rows, which also retain start/end frames, times, segment and maximum speed.

Heatmaps assign each valid interval's entire `dt` to its **starting position's
cell**. The grid uses that Match's dimensions in metres: X = length, Y = width.
This approximates observed residence time; it does not interpolate movement through
cells. Rejected rows, invalid intervals and segment gaps add no occupancy. Occupied
cells expose bounds, `occupancy_seconds` and `occupancy_fraction`; omitted cells
have zero occupancy. Total occupancy equals active duration and fractions sum to
approximately one when duration is positive. Zero-duration tracks return no cells.
Boundary-tolerance points use the edge cell without changing movement coordinates.

Four CSVs form one protected, attempt-specific bundle under
`storage/analytics/matches/<match_id>/videos/<video_id>/jobs/<job_id>/attempt-<attempt>-<uuid>/`:

- `players.csv`: one summary per track, including usable extents/counts, segment
  count, interval counts, distance, duration, speeds and sprint totals.
- `intervals.csv`: track/segment, start/end frame/time/cleaned position, `dt`,
  distance and speeds. `above_sprint_threshold` identifies threshold-qualified
  intervals; only `sprints.csv` identifies duration-qualified events.
- `sprints.csv`: the qualifying continuous sprint events.
- `heatmaps.csv`: sparse occupied cells with pitch bounds, seconds and fractions.

Rows stream in Phase 10 order, retaining bounded state and a grid for one track.
Only result/configuration/version metadata enters SQLite. Files are flushed in an
attempt-owned `.partial` directory, then one directory rename publishes the whole
bundle. A short Match lock and version checks before and after publication protect
completion. The database exposes the bundle only after success; failed attempts
clean their own outputs and leave previous complete results intact. All four files
are checked together on reads. Video, calibration, tracking, coordinates or the
exact trajectory result changing makes analytics stale; **team assignment changes
do not invalidate physical analytics**.

- `POST /api/matches/{match_id}/jobs/player-analytics` queues ProcessingJob/RQ and
  returns 202. Workers receive only job ID/attempt, report actual processed-row
  progress, and persist safe failures; there is no synchronous fallback.
- `GET /api/matches/{match_id}/player-analytics` returns lightweight track summaries
  with `offset`/`limit` pagination (default 25, maximum 100).
- `GET /api/matches/{match_id}/player-analytics/{track_id}` returns one summary.
- `GET /api/matches/{match_id}/player-analytics/{track_id}/heatmap` returns grid,
  pitch dimensions and sparse occupancy. Missing/stale results return 409, missing
  tracks 404, and invalid IDs 422. No paths, raw trajectories or CSV downloads are
  exposed.

Admin can run/read globally; Coach/Analyst can run/read accessible club matches.
Club Management is read-only. Player cannot inspect arbitrary Track IDs without a
verified identity association. Anonymous requests return 401; cross-club access is
denied by the backend.

Track IDs are not automatically named roster players; ID switches can split one
person's statistics. Missing movement cannot be recovered, and piecewise sampled
distance may underestimate real movement. Speed depends on timestamp/sample
resolution and upstream calibration quality. Sprint definitions depend on chosen
thresholds. Starting-cell heatmaps approximate observed occupancy, not exact
continuous location. Real-match accuracy is not formally evaluated, live
Redis/PostgreSQL deployment remains unverified, and no ball/event statistics or
team tactical analytics are included in Phase 11; team geometry is described below.

## Phase 12 — Team tactical analytics (backend)

Inputs are the **current Phase 10 cleaned trajectories and effective Phase 8 team
assignments**. Only `usable=true` clean positions contribute. A manual assignment
overrides the automatic label; Unknown and missing track assignments contribute
to neither team. At least one current assignment is required for nonempty tracking
results. No Phase 11 artifact is required, and no upstream processing is rerun.

Snapshots group by exact `frame_number`, preserving `timestamp_seconds`. A track
contributes once per frame; duplicate usable tracks or conflicting timestamps fail
the job. Usable segment-start positions contribute normally: team shape is
instantaneous. Frames with at least one usable trajectory row get a row for each
team, including zero-visible teams. Frames containing only rejected observations,
unobserved frames and gaps are not reconstructed.

`TACTICS_MIN_PLAYERS_PER_TEAM` defaults to **3** (configurable from 2 to 22).
Below that threshold, `sufficient_players=false`, visible count is retained, and
all geometry is null. Empty/all-Unknown/insufficient results complete with explicit
warnings and unavailable metrics. The threshold does not imply full-team visibility.
Pitch dimensions come from Match, in metres: **X = length; Y = width**.

| Metric | Definition for a sufficient snapshot |
| --- | --- |
| `centroid_x/y` | Mean X and Y of visible usable assigned tracks |
| `width_metres` | `max(Y) - min(Y)` |
| `depth_metres` | `max(X) - min(X)` |
| `compactness_radius_metres` | Mean Euclidean distance to the centroid |
| `mean_pairwise_distance_metres` | Mean distance over unique unordered player pairs |
| `convex_hull_area_m2` | OpenCV convex-hull area; null for fewer than three non-collinear positions |
| `bounding_box_area_m2` | Width × depth, distinct from hull area |
| `centroid_distance_to_opponent_metres` | Distance between centroids, only when both teams are sufficient |

Summaries use **equal weight per valid snapshot**, not duration weighting. This
avoids assigning long gaps to one shape. Insufficient snapshots and null values
are excluded, never substituted with zero; average visible count also uses valid
snapshots only. Hull and between-team metrics retain their own contributing counts.
Medians are not computed. The worker externally regroups track-ordered trajectories
in 4,096-row disk runs with bounded merge fan-in, streams frame metrics, and keeps
constant-size aggregates plus the assignment map and one frame's positions.

Two CSVs publish together under
`storage/team_analytics/matches/<match_id>/videos/<video_id>/jobs/<job_id>/attempt-<attempt>-<uuid>/`:
`team_tactics_frames.csv` holds frame/team metrics; `team_tactics_summary.csv` holds
one summary for each team. The shared bundle publisher flushes both files and uses
one directory rename. Failed attempts clean their temporary outputs and preserve
previous complete bundles. SQLite stores only job, provenance and result metadata.

ProcessingJob/RQ type `team_tactical_analytics` receives IDs/attempts and reports
actual processed-row progress. Trajectory provenance and a deterministic effective
assignment digest are captured at enqueue, checked at worker start, and rechecked
before/after publication under the same Match lock used by manual corrections.
Video, calibration, tracking, coordinate, trajectory or effective assignment
changes invalidate results. **Phase 11 reruns do not invalidate team analytics**;
confidence or automatic-label edits masked by an unchanged manual override do not
either. Failed retries cannot publish a mixed bundle.

- `POST /api/matches/{match_id}/jobs/team-tactical-analytics` queues the job (202).
- `GET /api/matches/{match_id}/team-analytics` returns both summaries and metadata.
- `GET /api/matches/{match_id}/team-analytics/{team}` returns one summary.
- `GET /api/matches/{match_id}/team-analytics/{team}/series` returns bounded frame
  rows with `offset`/`limit` (default 25, maximum 100); `team` is `team_a` or `team_b`.

Admin runs/reads globally; accessible Coach/Analyst run/read; Club Management reads
only; Player is denied. Anonymous requests return 401, cross-club access is denied,
invalid teams/pagination return 422, and missing/stale results return 409. No paths
or complete frame CSVs are exposed through these APIs.

Only visible tracked players contribute. Occlusion and Unknown assignments reduce
coverage; ID switches can change team membership and manual correction may be
needed. Calibration error propagates. Metrics describe visible geometry, not
tactical quality. Attacking direction, formations, substitutions and named-player
identity are not inferred. Real-match tactical accuracy and live Redis/PostgreSQL
operation remain unverified. Phase 13 provides the dashboard; tactical
recommendations are not included.

## Phase 13 — Match Analytics dashboard

Open **View Analytics** from Match Details, or visit
`/matches/:matchId/analytics` directly. The protected, lazy-loaded route has
Overview, Players, Team Tactics, Heatmap and Team Assignments tabs. Admin,
accessible Coach/Analyst and Club Management can view results. Club Management
is read-only; Player cannot access arbitrary Track-ID analytics. Existing backend
role and club checks remain authoritative.

Players shows backend distance in metres, active duration, average/maximum speed
in km/h, sprint count and sprint distance. Select a track for sprint duration,
segments and observation/interval coverage. Lists use 25-row pages with optional
sorting of the current page only. Null metrics show **Unavailable**. Track IDs
belong to a match and are not automatically associated with named players.

The shared SVG pitch renders backend heatmap cells using the returned pitch
dimensions, grid bounds and occupancy fractions. **X = length; Y = width**, with
origin at top-left. A labeled intensity legend describes observed cleaned
occupancy, not quality. Missing periods are not reconstructed; empty occupancy
has an explicit empty state. Interior pitch markings are schematic.

Team A/B cards compare valid/insufficient snapshots, visible players, centroid,
**width along Y**, **depth along X**, compactness radius, pairwise spacing,
convex-hull footprint, bounding-box area and opponent centroid separation.
Recharts displays width, depth, compactness and centroid X/Y over time, using
explicit windows of at most 100 snapshots per team. Null/insufficient snapshots
remain gaps; a text table exposes chart values. The browser formats and displays
these metrics without recalculating physical or tactical analytics.

Team assignment review separates automatic label/confidence, manual override
and effective team. Admin/Coach/Analyst can intentionally save Team A, Team B or
Unknown, or clear an override to restore the automatic label. Saves show pending,
success or safe error feedback. A successful save refreshes assignments and
Phase 12 tactics; stale tactics are hidden with **“Team assignments changed.
Regenerate team tactical analytics.”** Phase 11 physical analytics remain usable
and are not invalidated by assignment edits.

Explicit **Generate Player Analytics** and **Generate Team Tactical Analytics**
actions reuse ProcessingJob and the existing queue. Current trajectories and,
for team tactics, assignments are required. Active jobs show stage/progress and
use the existing two-second polling; terminal jobs stop polling. Failed jobs show
safe errors and permitted retries. Loading, missing, stale, empty and forbidden
states never substitute invented zeros. Opening the page starts no processing.

Production components use real backend responses only; synthetic fixtures are
confined to tests. Team geometry depends on visible, correctly assigned tracks;
Unknown assignments reduce completeness. Metrics are descriptive, with no
quality scores, rankings, inferred attacking direction or formations. Real-match
accuracy still depends on upstream detection, tracking, calibration and cleaning.
Ball/event metrics remain unimplemented. Reports and exports are described below.

## Phase 14 — Match PDF reports and CSV exports

Open **Match Analytics → Overview → Reports / Exports**. Select **Generate PDF
Report** explicitly; visiting the dashboard never starts a job. The existing
ProcessingJob/RQ queue runs `match_report` using only the job ID and attempt.
The panel reuses job polling for stages/progress, completion and safe retry errors,
then refreshes report status without invalidating unrelated analytics queries.
An active source video and editable Match are required to queue generation.

The A4 PDF contains actual Match/club/team metadata, pitch dimensions, generation
time, factual availability/counts, all analyzed tracks with effective team labels,
distance, active duration, average/maximum speed and sprint summaries. Team A/B
tables include snapshot coverage, centroid, width, depth, compactness, spacing,
footprint and centroid separation where available. **Width = Y range; depth = X
range.** Methodology and limitations accompany every report; no metric is
recalculated or coaching judgment inferred. Tables paginate with repeated headers.

Heatmaps read saved Phase 11 occupancy cells, using the Match's actual pitch
length (X) and width (Y). `REPORT_HEATMAP_LIMIT` defaults to **4** (allowed 0–12):
tracks with usable duration are selected in ascending Track ID, without ranking.
If either analytics family is unavailable/stale, the PDF labels it unavailable.
If both are unavailable, an informational report is generated with a job warning.
Unavailable numerical values remain unavailable or a labeled dash, never a fake
zero. Active duration is sampled usable duration, not minutes played.

Generation uses [ReportLab](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/)
with embedded fonts; [pypdf](https://pypdf.readthedocs.io/en/latest/modules/PdfReader.html)
validates signature/end marker, readable content streams and positive page count
before publication. Both libraries and their exact tested pins are declared in
`backend/requirements.txt` and `backend/requirements-dev.lock`; no external PDF
executable or browser printing is required. User text is escaped as plain text.

Report dependencies include rendered Match metadata, active video, effective
assignment hashes (manual overrides take precedence), and current Phase 11/12
job/attempt identities, provenance and artifact versions. Existing current-result
guards exclude stale inputs. Changed inputs, including previously unavailable
analytics becoming available, make an old report stale. Operational job metadata
and automatic labels masked by an unchanged manual override do not invalidate it.
The panel displays: **Analytics have changed. Regenerate the report to include
current results.**

Each PDF is an attempt-specific artifact under `storage/reports/matches/`.
Generation validates and rechecks dependencies under the existing Match lock
before atomic publication and job completion. Failed attempts clean their own
files; a prior successful PDF stays intact. Historical files are retained, but
the normal download endpoint serves only the current report and returns 409 for
missing/stale output. SQLite stores metadata/references, not PDF bytes. Storage
is not publicly mounted, and responses expose no filesystem locations.

| Method / Match endpoint | Behavior |
| --- | --- |
| `POST /api/matches/{id}/jobs/match-report` | Queue generation; return ProcessingJob (202) |
| `GET /api/matches/{id}/report` | Availability/current/stale state and safe summary |
| `GET /api/matches/{id}/report/file` | Protected PDF attachment |
| `GET /api/matches/{id}/exports/player-analytics.csv` | Current player summary plus effective team |
| `GET /api/matches/{id}/exports/team-analytics.csv` | Current Team A/B tactical summaries |

CSV exports use the existing schema fields only: 11 player columns and 15 team
columns, with metres, seconds and explicit speed units in headers. They use UTF-8,
standard quoting and blank unavailable numerical cells; no NaN/Inf/None strings,
P95 or invented medians. Unknown remains Unknown; unavailable assignment data is
blank. Formula-like textual prefixes (`=`, `+`, `-`, `@`, including after leading
whitespace) are escaped without changing negative numerical values. Small summary
exports are generated on demand and revalidated, without modifying source results.
Optional frame/interval CSVs and tactical time-series PDF plots are not included.

Admin can generate/download globally; Coach/Analyst can do so within club scope.
Club Management has read/download access only. Player and anonymous access are
denied; backend checks enforce cross-club boundaries. Downloads use bearer-authenticated
requests, safe logical filenames such as `footlytics-match-42-report.pdf`, and
temporary browser Blob URLs that are revoked after use.

Reports inherit upstream accuracy. Track IDs are not automatically roster-player
identities; heatmaps show observed cleaned occupancy and tactics describe visible
geometry, not coaching quality. Missing movement is not recovered. Attacking
direction, formations and ball/event metrics are not inferred. Real-match quality
depends on current processed inputs; Phase 15 external CV evaluation and its
coverage limitations are documented below.
Complex-script typography is not verified with the bundled fonts. Live Redis/RQ
delivery and PostgreSQL were not exercised by this phase's local checks.

## Phase 15 — Computer-vision evaluation

**Phase 15 is complete. Phases 16–17 are optional / deferred.** The existing evaluator now
has real results on three SoccerNet-GSR validation clips from three source games.
Production CV, thresholds and frontend functionality are unchanged.

Source: official [SoccerNet/SN-GSR-2025](https://huggingface.co/datasets/SoccerNet/SN-GSR-2025),
`valid.zip`, revision `ce84ee7d9acb2f9fe999ceed2b38e303ffa5efb9`.
Every selected annotation declares **version 1.3**. The public release was ungated.
Downloaded members passed ZIP CRC32/length checks and retain SHA-256 hashes;
the full 11.17 GB archive was not downloaded or hash-verified.

Selection used sorted validation metadata: first suitable clip per new source
game, frozen before inference. Every skipped clip (37 duplicate-game clips) is
recorded in `data/external/soccernet_gsr/manifests/selection.json`. No predictions,
jersey colours or apparent difficulty influenced selection.

| Clip | Source game | Frames | Scored GT boxes | GT/team-labelled identities |
| --- | --- | ---: | ---: | ---: |
| SNGS-021 | 2 | 150 | 2,250 | 15 / 15 |
| SNGS-039 | 3 | 150 | 2,653 | 21 / 21 |
| SNGS-078 | 5 | 150 | 1,700 | 13 / 13 |
| Total | 3 games | 450 | 6,603 | 49 / 49 |

Each interval is consecutive JPEGs `000001..000150` -> evaluator/production frames
`0..149`, 25 FPS, 1920 x 1080: six seconds each, **18 seconds total**. Every frame
through production `VideoFrames` matched its decoded source JPEG exactly:
**450 checked, 0 mismatches**. Early/middle/late GT overlays also aligned. Human
keyframe labels plus dataset interpolation provide boxes and persistent clip-local
IDs. Players/goalkeepers are scored; 642 referee boxes are explicit ignores.

Team mapping uses **jersey-color references extracted from human-labelled SoccerNet
team annotations**: fixed outfield crops on frames 0,15,30, median CIE Lab, ascending
(L,a,b). 021/039: left -> A, right -> B; 078: right -> A, left -> B. References,
mapping and settings were frozen before inference. No manual overrides,
accuracy-maximizing permutation or post-result threshold tuning were used.

| Clip | Detection F1 | AP50 | Tracking IDF1 | MOTA | Team accuracy / coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| SNGS-021 | 90.80% | 86.02% | 87.64% | 81.42% | 20.00% / 20.00% |
| SNGS-039 | 84.04% | 74.61% | 66.61% | 66.83% | 0% / 0% |
| SNGS-078 | 86.91% | 83.10% | 76.94% | 71.82% | 0% / 0% |
| Overall | 87.01% | 81.40% | 76.44% | 73.09% | 6.12% / 6.12% |

Detection at IoU >= 0.50: **5,642 TP, 723 FP, 961 FN**, precision 88.64%, recall
85.45%, mean matched IoU 0.7895. AP50 is all-points AP over saved confidence-filtered
predictions, not COCO mAP. Tracking uses motmetrics aggregation: **58 ID switches,
435 FP, 1,284 misses, 115 fragmentations**; MOTP is mean **1-IoU distance** 0.2065
(lower is better). Produced detection/track counts are separate diagnostics.

Automatic teams are the main weakness: **46/49 GT identities are Unknown (93.88%)**.
Only three receive a known team; classified-only accuracy of 100% describes those
three, not the whole sample. Team A precision is unavailable, recall/F1 are 0;
Team B precision is 100%, recall 11.54%, F1 20.69%. Per-clip class metrics and
confusion matrices remain visible. Unassociated GT identities count as Unknown.

**Calibration and pitch-coordinate accuracy are unavailable.** Selected line
polylines do not establish four verified fit correspondences plus separate held-out
landmarks, and there are no explicit camera-parameter records. Camera motion
prevents assuming one static calibration. No homography is fitted from player GT.
External pitch estimates are not surveyed positions. `coordinate_metrics.csv` is
intentionally omitted; null results include reasons.

Runtime: existing **WSL2 / Intel i5-1250P / 16 logical CPUs**, Python 3.14.4,
PyTorch 2.14.1+cpu, Ultralytics headless 8.4.170, OpenCV headless 4.14.0.94,
motmetrics 1.4.0, CUDA=False.

| Clip | Model construction s | Detection s / effective FPS | Tracking s | Teams s |
| --- | ---: | ---: | ---: | ---: |
| SNGS-021 | 0.354 | 16.919 / 8.866 | 0.311 | 40.078 |
| SNGS-039 | 0.352 | 16.702 / 8.981 | 0.345 | 69.274 |
| SNGS-078 | reused | 16.006 / 9.372 | 0.236 | 39.934 |

Stages plus model construction total **200.510 s**. Detection averages 9.068 FPS
including decoding, CSV writes and first-call lazy setup. Download/preparation,
input hashing, Python/torch imports and scoring are excluded. Model construction
and first/remaining YOLO-call timings are recorded separately. Bounded jersey-frame
seeking in lossless MOV on `/mnt/d` differs from compressed-upload performance.
The first clip was scored before the remaining two and reused without repeat YOLO.
No fourth/fifth clip was added.

The [real results overview](storage/evaluation/soccernet-gsr/20261005T190256Z-b2071b05c157/results_overview.md)
sits beside full JSON/Markdown results, detection/tracking/team/runtime CSVs,
confusion matrices, configuration/input/source/weights hashes and verification
evidence. Real predictions are cached in
`storage/evaluation_inputs/soccernet-gsr-distinct-games-v1/`. Source media,
annotations, weights and results remain ignored by Git and outside SQLite.

Reproduce scoring from existing frozen inputs in WSL, without rerunning YOLO:

```bash
cd '/mnt/d/VS Projects/FYP_Footlytics/backend'
source /home/sabeeh/.venvs/footlytics-yolo/bin/activate
python -m app.evaluation.soccernet_report \
  --dataset ../data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --predictions ../storage/evaluation_inputs/soccernet-gsr-distinct-games-v1/predictions.json \
  --output ../storage/evaluation/soccernet-gsr
```

[The annotation guide](data/annotations/README.md) preserves manual/CVAT instructions
and adds SoccerNet preparation and bounded production-run commands. The generic
CLI remains `python -m app.evaluation.run --help`. Synthetic evaluator outputs
stay explicitly marked and separate from real scores.

This small sample is moving-camera broadcast 11v11 footage. Zoom, resolution,
compression, player scale, lighting and stadium conditions limit transfer to
arbitrary user recordings or 5v5. It does not establish broad football accuracy,
full-match identity stability, reliable team assignment or real trajectory accuracy.
These are local metrics, not an official SoccerNet leaderboard submission.

## Checks

Phase 18 final verification: **1,079 backend tests passed, 0 failures/errors/skips,
600.96 seconds**, one full run with four existing JUnit metadata warnings.
**143 frontend tests passed** after the home-page guidance fix; ESLint, TypeScript
and production build passed. Ruff and format (211 files), unique/current Alembic
head and WSL API health passed. Browser evidence includes **55 live checks** and
**40 explicitly fixture-based viewport checks**; all eight real PDF pages were
rendered and inspected. See [the complete record](docs/PHASE18_VERIFICATION.md).

UI redesign verification (branch `feature/ui-redesign`, Stage 9): **243 frontend
tests passed** in two consecutive full runs; ESLint, TypeScript and the production
build passed with no chunk over 500 kB. The backend was not changed: **1,215 tests
passed** (687 seconds), Ruff check/format passed and Alembic has the single head
`0015_team_color_prototypes`. A Playwright/Edge sweep passed **178/178 checks** at
390, 834, 1440 and 1920 px plus a short landscape view; performance checks (16/16)
and API-level role checks (53/53) also passed. An isolated end-to-end run re-ran all
nine processing jobs through Redis/RQ with the CPU YOLO model on a copy of the
Phase 18 QA data. Detection, tracking, coordinates, trajectories, player analytics
and heatmaps matched the saved results exactly; after the original manual team
overrides (tied to a tracking run) were re-applied, team tactics and both CSV
exports matched too, and the new PDF differed only in its timestamp and job IDs.
The QA clip is a controlled still frame, so this shows integration and
repeatability, not motion or coordinate accuracy. Details:
[docs/UI_REDESIGN.md](docs/UI_REDESIGN.md).

Use the activated WSL environment. From the repository root:

```bash
python scripts/check_structure.py
python -c "import sys; sys.path.insert(0, 'backend'); from app.main import app; print(app.title)"
cd backend
python -m ruff check app tests alembic ../scripts
python -m ruff format --check app tests alembic ../scripts
python -m pytest -q --tb=short
```

Run Ruff from `backend/`, as shown, so its existing project/import discovery is
consistent with the repository configuration. Normal tests use temporary SQLite
databases, tiny generated clips and injected
queue/model boundaries. They need no model download, running Redis or full match.
Migration round-trips and schema drift checks use isolated databases. Model-backed
smokes and external evaluation are explicit opt-in work, separate from pytest.

Frontend, in PowerShell from `frontend/`:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

The existing build script runs **`tsc -b` then `vite build`**, so it includes the
TypeScript check. On a memory/CPU constrained development machine use
`npm.cmd test -- --maxWorkers=1` to run unchanged tests serially; avoid competing
CV workloads during UI tests. Existing local Playwright/Edge scripts under
`.tools/browser-check/` exercise viewport and failure states using explicitly
marked fixtures. Phase 18 also uses real API/browser checks without interception.

Phase 15 evidence is retained: **118 focused tests, 227 CV regressions, 1,079 full
backend tests passed, 0 failures/errors/skips** (611.22 seconds); four existing JUnit metadata
warnings. Evaluation artifacts include `verification.json`; the measured results
above are unchanged. Phase 18 final results and evidence are recorded in
[docs/PHASE18_VERIFICATION.md](docs/PHASE18_VERIFICATION.md).

## Demonstration workflow

Use [DEMO_GUIDE.md](DEMO_GUIDE.md) for service commands and a 5–10 minute sequence.
Create a club, two distinct same-club teams, players/squad membership and a match.
Set that match's actual pitch length/width. Upload and prepare a supported football
video, select a frame and save at least four valid image/pitch correspondences.
Run detection, tracking and classification; review previews and correct team
assignments as needed. Then map coordinates, clean trajectories and run player
and team analytics. Use Match Analytics for player metrics, heatmaps, team
geometry and report/CSV downloads. Wait for each required upstream job to finish.
Replacing a video or changing calibration/tracking invalidates downstream results;
team edits invalidate relevant tactics/reports while preserving physical metrics.
Never present a controlled stationary QA clip as real player movement evidence.

## Known limitations and deferred features

- Static planar homography assumes a fixed camera and valid landmarks. Broadcast
  pans/zooms invalidate that assumption. Coordinate accuracy has **not** been
  independently benchmarked; four-point fitting residual is not validation error.
- SoccerNet evaluation covers 18 seconds from three broadcast 11v11 games. It does
  not establish broad 5v5, user-footage or full-match performance. Automatic jersey
  coverage was only **6.12%**; **46/49 identities were Unknown**. Manual corrections
  are explicit user inputs, separate from automatic evaluation.
- CPU processing is supported but is not real time. Occlusion and identity
  switches remain; track IDs are match-specific and are not linked to named
  Player accounts. Analytics describe observed, cleaned movement/visible geometry.
- Phases 16 and 17 are **OPTIONAL / DEFERRED**: ball tracking is outside the core
  FYP, and possession/pass/shot inference depends on reliable ball tracking.
  No ball/event analytics or xG is claimed.
- SQLite/WSL is validated. PostgreSQL deployment remains future work. External
  ffprobe was absent during local verification; the real OpenCV fallback works,
  while codec/container metadata remains unavailable with a warning.
- Health is a liveness check. A production deployment still needs its own HTTPS,
  backup and service supervision configuration.
- The API exposes per-track heatmaps and per-team snapshot series, not per-player
  trajectory rows, so the UI draws team centroid paths rather than individual
  player trajectories. Review previews are backend-annotated JPEGs: there is no
  client-side box overlay or track filtering, and the detection and tracking
  viewers step independently. The match list shows no per-match processing state
  (the list API has none and per-row requests were deliberately avoided).
- Automated accessibility checks are custom Playwright audits (accessible names,
  labels, alt text, duplicate IDs, headings, focus); no axe-core colour-contrast
  audit is part of the repository tooling.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Windows `c10.dll` / WinError 1114 | Run backend/CV in the documented Linux CPU venv; do not reuse the Windows venv. |
| API rejects JWT settings | Replace the example `JWT_SECRET` with a private random value; restart API and worker. |
| Missing tables / schema errors | Activate the same environment, check `DATABASE_URL`, and run Alembic upgrade/current/check. |
| 503 queue unavailable | Check `redis-cli ping`, `REDIS_URL` and queue settings, start Redis, then use the job's Retry action. |
| Job remains queued | Start `python scripts/run_worker.py` in WSL with the same database/storage/queue settings. |
| Job fails | Read its safe UI error and worker log; fix the cause, then retry. A retry gets a new attempt and preserves valid history. |
| Stale or unavailable result | Complete the current required upstream stages. Replacing a video requires new calibration and processing. |
| API unavailable in browser | Check health, Vite's API proxy target and Windows-to-WSL localhost forwarding. |
| Codec/container unavailable | Install FFmpeg/ffprobe or use the validated OpenCV fallback; do not invent the metadata. |
| Poor team labels | Review explicit Unknown assignments and apply authorized manual corrections; regenerate affected tactics/reports. |
| Login lost after closing tab | Sessions intentionally use `sessionStorage`; reload persists, logout/closing the tab ends that browser session. |

## Local data and repository hygiene

`.env`, dependencies/environments, local tooling, SQLite files, Redis persistence,
logs, builds, videos, weights and generated storage/evaluation data are ignored.
Keep validated evaluation outputs, annotations and provenance available locally
for the report; do not delete them as cleanup. Back up the database **and** its
referenced storage together before moving/deploying a working installation.
Human-readable evaluation documentation and small test fixtures remain source.
