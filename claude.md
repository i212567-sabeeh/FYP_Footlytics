# FOOTLYTICS — Claude Code Project Instructions

## Project

FOOTLYTICS is a football video analytics Final Year Project developed using React/Vite, FastAPI, SQLite/Alembic, Redis/RQ, Ultralytics YOLO, ByteTrack, OpenCV, and associated analytics/reporting components.

The goal is to analyze football match videos using computer vision and produce player tracking, team classifications, pitch coordinates, match analytics and downloadable reports.

## Current Status

- Core project implementation is complete.
- Phases 1–15 and Phase 18 form the completed core scope.
- Phases 16–17 are optional/deferred.
- Do not assume deferred phases must be implemented.
- Phase 18 was the final stabilization, integration and verification phase.

### Latest Verified Baseline

- Backend full suite: 1,079 passed.
- Focused backend suite: 231 passed.
- Frontend suite: 143 passed.
- Browser checks: 55 passed.
- Viewport checks: 40 passed.
- Ruff, ESLint, TypeScript and frontend build passed.
- Alembic migrations and FastAPI health verified.
- Redis/RQ worker and failure/retry behavior verified.
- End-to-end integration tested across detection, tracking, analytics, PDF and CSV outputs.
- Eight report PDF pages visually verified.

These are historical verification results, not a guarantee that the current working tree is unchanged. Revalidate when necessary.

## Architecture

- Frontend: React, Vite, TypeScript.
- Backend: Python, FastAPI.
- Database: SQLite with Alembic migrations.
- Background processing: Redis/RQ.
- Computer vision: Ultralytics YOLO, ByteTrack and OpenCV.
- Processing outputs: structured CSV artifacts and reports.
- Runtime: Windows development environment with WSL2 Ubuntu for CV-related execution.

Read the actual repository for precise implementations, versions, configuration and commands.

## Existing Documents

Use these as the source of truth:

1. README.md
2. IMPLEMENTATION_PLAN.md
3. docs/ARCHITECTURE.md
4. DEMO_GUIDE.md
5. Relevant phase documentation and tests.

Read only documents and source files relevant to the active task. Do not load the entire repository into context unnecessarily.

## Development Rules

1. Inspect existing implementations before making changes.
2. Preserve current architecture and conventions.
3. Avoid unnecessary refactoring.
4. Do not regenerate or rewrite completed components without justification.
5. Never delete existing features to simplify a task.
6. Preserve API contracts, migrations and data compatibility.
7. Use existing utilities and patterns whenever possible.
8. Write or update focused tests for changed behavior.
9. Run focused verification before expensive full-suite validation.
10. Do not claim tests have passed unless they were actually executed.
11. Ask before making destructive or high-risk changes.
12. Never expose or commit credentials, secrets or private environment files.

## Token Efficiency

- Keep responses concise.
- Avoid repeating previously established context.
- Search targeted directories and filenames before opening files.
- Avoid dumping large source files or logs into conversation.
- Read relevant file sections wherever possible.
- Do not repeatedly reread unchanged files.
- Do not launch broad multi-agent investigations unless justified.
- Reuse existing docs rather than reconstructing architecture.
- Prefer narrow changes over extensive rewrites.
- Report concise summaries of edits and test outcomes.
- When switching unrelated tasks, recommend starting a fresh session.

## Current Working Goal

Maintain, verify and improve the completed FOOTLYTICS system. Prioritize correctness, demonstration readiness, performance and FYP evaluation quality. Do not automatically begin new phases or large features without a specific request.