# FOOTLYTICS development rules

Read the existing code, README.md and IMPLEMENTATION_PLAN.md before changing the
project. Implement only the phase the user requests and preserve working modules.

## Scope and architecture

- Post-match analysis of recorded 11v11 and 5v5 football footage; CPU support is
  mandatory. CUDA acceleration is optional. Prefer pretrained models.
- React + strict TypeScript + Vite, React Router, TanStack Query and Tailwind CSS.
  Add shadcn/ui and Recharts when their features are needed.
- FastAPI + Pydantic; SQLAlchemy + Alembic; SQLite for development, PostgreSQL later.
- Redis + RQ + a separate Python worker for long jobs. Never process a video in an
  HTTP request. Future processing endpoints create a job, enqueue it and return
  its ID; the frontend polls status. Persist job failures without exposing traces.
- Keep HTTP handlers, services, ORM models, schemas, auth, CV, analytics, workers
  and report generation in their existing separate packages.
- Store large files under storage/, with metadata and paths in the database.
  Never store videos as database blobs or expose storage as an unprotected mount.
- Use centralized settings; no committed secrets. Backend authorization must
  enforce resource access, regardless of frontend visibility.

## Scientific invariants

- Pitch coordinates are metres: X = length, Y = width. Each match stores its own
  pitch_length_metres and pitch_width_metres; no global pitch dimensions.
- Player ground point is the bounding-box bottom centre:
  ((x1 + x2) / 2, y2), never the box centre.
- Calibration needs at least four valid landmark correspondences. Account for
  calibration validity and camera motion before interpreting positions as metres.
- ByteTrack is the default tracker behind a replaceable abstraction. IDs belong
  to one match only. No face recognition or cross-match biometric identification.
- Jersey classification supports Team A, Team B and Unknown. Coaches/analysts
  may correct team assignments; manual football-event annotation is out of scope.
- Never fabricate analytics. Missing or invalid data means Unavailable / an empty
  state. Mock data belongs only in explicitly marked development tests/fixtures.
- Ball/event features are optional and cannot block player analytics. Never invent
  an xG formula. Only a legitimate model with available required inputs may be used.
- No custom model-training pipeline unless explicitly requested.

## Implementation practice

- Inspect for existing components, clients, settings and services before adding
  new ones. Extend them instead of creating competing implementations.
- Use small functions, Python type hints and strict TypeScript without unnecessary
  any. Explain non-obvious algorithms and metric definitions for the FYP viva.
- Test major features with pytest or Vitest/React Testing Library using small
  fixtures; normal tests must not process full matches or need model downloads.
- Run relevant checks and fix failures. Do not silently swallow exceptions.
- Keep infrastructure understandable: no microservices, Kubernetes or event bus.
- Keep runtime databases, media, weights, logs, reports, exports, Redis data,
  environments and dependencies out of Git.

Phases 1–3 provide authentication, administration and football-domain management.
Use the existing SQLAlchemy sessions, Alembic migrations, password/token helpers,
role dependencies, frontend auth provider and centralized API client. Do not add
parallel auth systems. Reuse auth/club_access.py for scoped list/count and detail
queries: global roles grant capabilities; club memberships grant resource scope.
Admin access is global. Backend permissions must never depend on frontend hiding.
User is a login account; Player is a footballer, optionally linked one-to-one to an
active account assigned to the same club. A Player is not a CV track identity.
Team and player clubs are immutable in this phase. Squad membership keeps history;
ending one must not delete the player. Domain records deactivate/archive instead
of hard deletion. Match teams must be distinct and in the same club. Pitch
dimensions belong to Match and remain configurable; X is length, Y is width.

Phase 4 adds MatchVideo, ProcessingJob, streamed uploads, safe storage, bounded
video inspection and a separate Redis/RQ video-preparation worker. Reuse these
services and the existing auth/club scope for later media features. Files belong
to matches; one active source is enforced by the database. Store only generated
relative paths internally and never expose filesystem locations through the API.
Reject unsafe names, enforce upload limits while streaming, decode a real frame,
and clean temporary files on failure. Validate replacements before publication;
retain retired sources for job history. Replacement and job creation/retry share
the short match-row transaction lock, with access rechecked after slow upload I/O.
Future calibration/results must reference video_id and become stale on replacement.
Do not treat preparation completion as calibration or analytics availability.

Long processing must use the job queue. Workers receive IDs and an attempt number,
never ORM objects, file handles or request sessions. Keep API and worker queue name,
JSON serializer, database and storage configuration aligned. Persist safe failures
and log developer details; Redis failure must never cause synchronous CV fallback.
Protect retry attempts against stale/duplicate delivery. Player access excludes
internal job management; Club Management is read-only. Run the RQ worker in Linux/
WSL. Normal tests inject the queue and use tiny generated clips without Redis or
model downloads. Do not start calibration, CV analysis, analytics or reports until
asked.
