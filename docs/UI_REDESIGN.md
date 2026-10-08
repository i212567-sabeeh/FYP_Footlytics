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
| 7 | Pitch visualisations, calibration workspace, heatmap, centroid paths | see log |

## Checkpoint log

- **Stage 5** — analytics workspace; 220/220 frontend tests; 63/63 browser checks; ac4330b (+7b68cfe line endings).
- **Stage 6** — review workspace, processed-frame navigation, cancellation and blob cleanup;
  231/231 frontend tests; 72/72 browser checks; 44630b8.
- **Stage 7** — shared pitch (`components/FootballPitch.tsx`, `pitchGeometry.ts`): exact
  metre viewBox, mowing bands, capped standard markings, no SVG text; calibration
  workspace (step guide, distinct frame/pitch markers, orientation labels, saved
  quality details and homography); heatmap palette, legend and most-occupied cells;
  team centroid paths from the existing team series (no per-player trajectory
  endpoint exists). Next: Stage 8 (authentication and management pages).
