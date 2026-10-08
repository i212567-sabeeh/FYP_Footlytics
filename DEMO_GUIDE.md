# FOOTLYTICS demonstration guide

Core scope: Phases 1–15 plus Phase 18. Ball tracking and possession/pass/shot
inference (Phases 16–17) are intentionally **OPTIONAL / DEFERRED**. Use the setup in
[README.md](README.md) first; this guide assumes migrations and an administrator
already exist. Choose and retain your own password privately.

## Before the demo

Prepare a short fixed-camera clip with visible verified pitch landmarks, or reuse
an already processed match and explain which outputs were prepared in advance.
CPU processing can exceed a 5–10 minute demo, so precompute the long stages.
Keep an untouched copy of the source and back up the database plus its storage.
The Phase 18 still-frame QA clip is labelled controlled integration and must not
be presented as real player motion or a coordinate-accuracy benchmark.

In Ubuntu, check Redis:

```bash
redis-cli ping
```

If it is not running, keep this command in a separate Ubuntu terminal:

```bash
redis-server --bind 127.0.0.1 --port 6379
```

Start the backend in another Ubuntu terminal:

```bash
cd "/mnt/d/VS Projects/FYP_Footlytics"
source "$HOME/.venvs/footlytics-yolo/bin/activate"
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Start the worker in another Ubuntu terminal, with the same root `.env`:

```bash
cd "/mnt/d/VS Projects/FYP_Footlytics"
source "$HOME/.venvs/footlytics-yolo/bin/activate"
python scripts/run_worker.py
```

Start Vite in Windows PowerShell:

```powershell
Set-Location 'D:\VS Projects\FYP_Footlytics'
# This workstation only, when Node is not on PATH:
$nodeTools = Get-ChildItem .tools/node -Directory | Select-Object -First 1
$env:Path = $nodeTools.FullName + ';' + $env:Path
Set-Location frontend
npm.cmd run dev
```

Verify `http://127.0.0.1:8000/api/health`, `/docs`, and the frontend at
`http://127.0.0.1:5173`. Use the existing administrator at `/login`. If one is
needed, the activated Ubuntu command is:

```bash
python scripts/create_admin.py --email admin@example.com --name "FOOTLYTICS Admin"
```

Run it from the root and choose an 8–128 character password at the secure prompts.
No password belongs in this guide, screenshots or the source repository.

For the signup flow, open `/signup` from the login page and submit an access
request with one non-admin **Requested role**. Sign in as administrator, open
**Access requests**, confirm that role, optionally assign a club, and approve it. The applicant can then sign in with their chosen password.
Pending/rejected requests cannot sign in; approval notifications are manual.

## A 5–10 minute presentation

| Time | Demonstration |
| --- | --- |
| 0–1 min | Sign in; show navigation, club scope and administrator user management. |
| 1–2 min | Show club, two teams, a Player/squad record and a match with its own pitch dimensions. Explain that named players are separate from CV track IDs. |
| 2–3 min | Show uploaded video metadata, **Video Prepared ✓**, collapsible Processing History and saved calibration. Identify the actual image/pitch landmarks and discuss the fixed-camera assumption. |
| 3–4 min | Open Detection & Tracking Review. Load a selected frame with real detection boxes and match-specific track IDs. Show asynchronous job progress/history. |
| 4–5 min | Review classification mode and Team A/Team B/Unknown labels. Open Set Team Colors for real crop examples or demonstrate a manual correction. Explain that tactics/reports then require matching effective assignments; avoid editing the prepared match unless ready to recompute. |
| 5–7 min | Open Match Analytics: player metrics, track detail, heatmap and team tactics. Explain units, observed coverage and null/unavailable values. |
| 7–8 min | Show current PDF, download/open it, then download player and team CSVs. Reports consume saved results and preserve historical artifacts. |
| 8–10 min | Show the separate Phase 15 SoccerNet summary and its limitations; demonstrate logout or a read-only role. |

To process a new match, follow the order: upload/preparation → calibration → YOLO
→ ByteTrack → jersey classification/manual review → coordinate mapping → trajectory
cleaning → player analytics and team tactics → dashboard/report. The UI/API will
reject missing or stale prerequisites; wait for completion before the next stage.
Team classification and coordinate mapping both depend on current tracks; physical
analytics does not require a team label. Never imply that an earlier completed
job automatically makes every later result available.

## Explain the scientific choices

YOLO detects people. ByteTrack associates saved image-coordinate detections across
frames. The bounding-box **bottom centre** estimates ground contact. Homography
maps that point to each match's pitch dimensions in metres. Cleaning flags invalid
positions and implausible continuity while retaining raw evidence. Physical
metrics use usable cleaned intervals; tactical metrics summarize visible assigned
team geometry. Unknown assignments and unavailable data remain explicit. Normal
reports do not contain invented match narratives or hidden ground-truth metrics.

SoccerNet was used for a separate real CV evaluation: 450 frames, 18 seconds, three
different broadcast games. Detection precision/recall/F1 were 88.64%/85.45%/87.01%,
AP50 81.40%; tracking IDF1 76.44%, MOTA 73.09%, with 58 ID switches. Automatic team
coverage was **6.12%** and **46 of 49 identities were Unknown**. Classified-only
accuracy was 100% over just three identities; it is not evidence of reliable team
coverage. Full provenance and metrics are linked in README.

## State the limitations openly

- Static planar homography does not compensate for camera pan, zoom or movement.
- No independent coordinate-accuracy benchmark was established. A calibration
  fitting residual is not held-out metre accuracy.
- Automatic jersey classification coverage was poor on SoccerNet; explicit manual
  correction is useful but is separate from automatic evaluation.
- CPU processing is not real time. Occlusion/ID switches affect track continuity.
- Evaluation covers only 18 seconds from three broadcast 11v11 games; it does not
  establish broad 5v5, arbitrary user-footage or full-match performance.
- No ball tracking, possession, passes, shots or xG are implemented.
- Visible-team geometry is descriptive and does not infer tactical quality.

If a stage is unavailable during the demo, show its real state and explain the
missing prerequisite. Never substitute fabricated results or label fixture data
as measured football performance.

## Hardening demo notes

After `alembic upgrade head`, restart the API and worker; a stale API process can
reject the signup form's `requested_role`. Keep the existing quoted WSL repository
path and Linux virtual environment used above.

In Team Assignments, **Set Team Colors** accepts several real examples per team.
For the controlled 60-second experiment the user specified **Team A = blue;
Team B = white**. This is user-seeded color mapping, not inferred club identity.
Preview a usable torso at a current Track ID/frame, add examples to both teams,
save prototypes, then queue classification. It uses saved tracks and video crops;
no new detection job is needed. Manual overrides remain authoritative.

Explain the limits while showing heatmaps: fragment coverage is relative to the
source video, gaps add no occupancy, and stitching was not adopted. The controlled
full-frame experiment classified only 3/251 tracks using seeded white examples;
no blue track met the unchanged repeated-evidence requirement.

The development five-minute results were made stale by older duplicate preparation
jobs changing the video's update timestamp. They were preserved, not relabelled as
current. Browser QA reused the matching pre-duplication database snapshot in an
isolated copy; it did not restore/overwrite the live database. To regenerate a
current five-minute dashboard, queue team classification and coordinate mapping using the current saved tracks,
then cleaning, player analytics, team tactics and reports. Do not rerun YOLO
or tracking for this timestamp-only staleness. The frozen Phase 15 evaluation stays
separate. See [the full hardening record](docs/HARDENING.md).
