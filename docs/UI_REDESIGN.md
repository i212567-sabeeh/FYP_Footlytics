# FOOTLYTICS UI redesign ("Matchday Control Room")

The frontend redesign runs on branch `feature/ui-redesign`; `main` stays at the
stable upload commit until the owner reviews and merges. Every stage keeps the
existing routes, API contracts, RBAC rules, CV/analytics calculations and the
accessible names that the tests rely on. No value shown in the UI is invented:
missing or stale results stay "Unavailable", "Not generated" or "Needs regeneration".

## Design system

- Dark navy/charcoal surfaces (`canvas`, `surface`, `surface-raised`), `line`
  borders and restrained emerald accents, defined as Tailwind v4 tokens in
  `frontend/src/styles.css`.
- Shared building blocks: `.panel`, `.button-primary/secondary`, `.icon-button`,
  `.field-input`, `.analytics-table`, `.progress-bar`, `.frame-scrubber`,
  `StatusBadge`, `AvailabilityBadge`, `Note`, `Metric`/`MetricRow`, and page
  headers with an eyebrow, title, context chips and actions.
- Team identity colours: Team A sky, Team B amber, Unknown slate.
- Lucide icons are decorative (`aria-hidden`); every control keeps a text name.

## Stages

| Stage | Scope | Commit |
| --- | --- | --- |
| 0–1 | Visual baseline, design tokens and shared UI | 5f730ed |
| 2 | Application shell, sidebar, breadcrumbs, mobile navigation | b82507f |
| 3 | Dashboard | 698fa89 |
| 4 | Match list, match header, evidence-based processing pipeline | 4d2a366 |
| 5 | Analytics workspace (overview, players, tactics, processing, reports) | ac4330b, 7b68cfe |
| 6 | Detection & tracking review workspace and frame navigation | 44630b8 |
| 7 | Pitch visualisations, calibration workspace, heatmap, centroid paths | b731f18 |
| 8 | Authentication, users, access requests, clubs, teams, players, squads | 729797c |
| 9 | Final QA, accessibility and performance fixes, documentation, end-to-end verification | 2cee1ce, d8c70fd |

## Checkpoint log

- **Stage 5** — analytics workspace; 220/220 frontend tests; 63/63 browser checks; ac4330b (+7b68cfe line endings).
- **Stage 6** — review workspace, processed-frame navigation, cancellation and blob cleanup;
  231/231 frontend tests; 72/72 browser checks; 44630b8.
- **Stage 7** — shared pitch (`components/FootballPitch.tsx`, `pitchGeometry.ts`): exact
  metre viewBox, mowing bands, capped standard markings, no SVG text; calibration
  workspace (step guide, distinct frame/pitch markers, orientation labels, saved
  quality details and homography); heatmap palette, legend and most-occupied cells;
  team centroid paths from the existing team series (no per-player trajectory
  endpoint exists); 238/238 frontend tests; 58/58 browser checks; b731f18.
- **Stage 8** — sign-in/sign-up card with product context and password visibility
  toggles; user management table (role badges, status pills, pinned actions on
  small screens) and sectioned user form; access-request cards and review panel;
  clubs/teams/players lists with filter cards and record rows, detail headers,
  club-access removal confirmation, squad table; shared `MessagePanel` for access
  denied, not found and session errors. 242/242 frontend tests; 86/86 browser
  checks including coach, Club Management and player role checks; 729797c.
- **Stage 9** — frame navigation keeps keyboard focus when First/Previous/Next/Last
  becomes disabled at a boundary (focus moves to the frame scrubber); the sidebar
  link list scrolls on short landscape screens instead of hiding behind the
  account area; React, React Router and TanStack Query share a `vendor` chunk so no
  chunk exceeds 500 kB; README, DEMO_GUIDE, ARCHITECTURE and IMPLEMENTATION_PLAN
  updated; 2cee1ce. d8c70fd restored the original CRLF endings of four files that
  Stages 1–4 had rewritten with LF, so the branch diff against `main` contains no
  line-ending-only changes. Results below.

## Final verification (Stage 9)

All results were executed on this workstation; nothing below is estimated.

| Check | Result |
| --- | --- |
| Frontend (Vitest) | 243/243 passed in two consecutive full runs |
| ESLint, TypeScript (`tsc -b`), production build | Passed; largest chunk `AnalyticsPage` 448 kB (131 kB gzip), `vendor` 301 kB, entry 204 kB |
| Backend pytest (unchanged by the redesign) | 1,215 passed in 687 s |
| Ruff check / format, Alembic | Passed / 227 files formatted / single head `0015_team_color_prototypes` |
| Final browser sweep (Playwright, Edge) | 178/178: 19 routes at 390, 834, 1440 and 1920 px plus 5 routes at 844×390 landscape (81 screenshots); no horizontal overflow, accessibility audit clean, skip link first in tab order, no unexpected writes, failed reads or browser errors |
| Performance (production build) | 16/16: no duplicate API requests on 7 routes; the Analytics chunk loads only on its route; review frame object URLs are revoked on every frame change and when leaving the page |
| API-level RBAC (QA copy) | 53/53: staff can read results, players cannot; another club's match returns 404; user, club and access-request administration is admin-only; Club Management and players cannot queue jobs, save calibration or override teams; anonymous requests return 401 |
| Security scan | No credentials, tokens, databases, videos, model weights or runtime artifacts tracked or in history; QA password and JWT secret absent from tracked files, history and the built bundle |
| End-to-end CV run (isolated copy) | See below |

The end-to-end run copied the Phase 18 QA database and storage, started a private
Redis, the API and burst RQ workers, re-saved the existing four-point calibration
(which correctly made detections stale) and ran all nine jobs with the established
CPU YOLO model: preparation, detection, tracking, team classification, coordinate
mapping, trajectory cleaning, player analytics, team tactics and the report. Every
job completed (five with their expected warnings: no ffprobe, no four-corner pitch
polygon, weak jersey evidence, retained unusable observations, team geometry
unavailable before manual labels). Detection, tracking, coordinate and trajectory
summaries, and all 19 tracks' analytics and heatmaps, matched the original saved
results exactly (15 tracks have heatmap cells). Automatic classification was again
19/19 Unknown; the original Team A/B labels were manual overrides tied to the old
tracking job, so they were re-applied through the API. Team tactics, both team
series and both CSV exports then matched exactly, and the regenerated 8-page PDF
differed only in its generation time and source job IDs. The clip is a controlled
still frame: this verifies integration and repeatability, not real player motion
or coordinate accuracy.

Screenshots and evidence (git-ignored) are under `.tools/ui-redesign/`: `before`
and `after` (Stages 0–1), `stage2` to `stage8` with `stageN-before` baselines and
`compare-stageN` side-by-side images, `final` for the Stage 9 sweep, `e2e` for the
end-to-end results and `scripts` for the verification scripts.

Known limitations: no per-player trajectory endpoint (team centroid paths only),
backend-annotated preview JPEGs without client-side overlays, no per-match status
in the match list, and custom Playwright accessibility audits rather than an
axe-core colour-contrast audit.
