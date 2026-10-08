"""Check the established layout through video storage and background jobs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DIRECTORIES = {
    "frontend/src": (
        "api assets components features hooks layouts pages routes types utils"
    ).split(),
    "backend/app": (
        "api analytics auth core cv database models reports schemas services workers"
    ).split(),
    "backend": ["tests", "alembic/versions"],
    "storage": "raw processed tracks analytics calibration reports exports".split(),
    "data": "validation_clips annotations sample".split(),
    ".": ["scripts", "docker"],
}
FILES = [
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "IMPLEMENTATION_PLAN.md",
    "docker-compose.yml",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/vite.config.ts",
    "frontend/src/main.tsx",
    "backend/requirements.txt",
    "backend/app/main.py",
    "backend/app/core/config.py",
    "backend/alembic.ini",
    "backend/alembic/env.py",
    "backend/alembic/versions/0001_users_and_roles.py",
    "backend/app/database/base.py",
    "backend/app/database/session.py",
    "backend/app/database/dependencies.py",
    "backend/app/models/user.py",
    "backend/app/auth/dependencies.py",
    "backend/app/api/auth.py",
    "backend/app/api/users.py",
    "frontend/src/features/auth/AuthProvider.tsx",
    "frontend/src/pages/LoginPage.tsx",
    "frontend/src/pages/UsersPage.tsx",
    "scripts/create_admin.py",
    "backend/alembic/versions/0002_clubs_teams_players_matches_clubs_teams_players_matches.py",
    "backend/app/models/football.py",
    "backend/app/schemas/football.py",
    "backend/app/auth/club_access.py",
    "backend/app/services/club_service.py",
    "backend/app/services/team_service.py",
    "backend/app/services/player_service.py",
    "backend/app/services/squad_service.py",
    "backend/app/services/match_service.py",
    "frontend/src/pages/ClubsPage.tsx",
    "frontend/src/pages/TeamsPage.tsx",
    "frontend/src/pages/PlayersPage.tsx",
    "frontend/src/pages/MatchesPage.tsx",
    "backend/alembic/versions/0003_match_videos_processing_jobs_match_videos_processing_jobs.py",
    "backend/app/models/media.py",
    "backend/app/schemas/media.py",
    "backend/app/api/videos.py",
    "backend/app/api/video_upload.py",
    "backend/app/api/jobs.py",
    "backend/app/services/storage_service.py",
    "backend/app/services/upload_service.py",
    "backend/app/services/video_inspection.py",
    "backend/app/services/video_decode.py",
    "backend/app/services/job_service.py",
    "backend/app/workers/queue.py",
    "backend/app/workers/video_preparation.py",
    "frontend/src/features/media/MatchMediaSections.tsx",
    "scripts/run_worker.py",
]


def main() -> int:
    missing = [
        str(Path(parent) / child)
        for parent, children in DIRECTORIES.items()
        for child in children
        if not (ROOT / parent / child).is_dir()
    ]
    missing.extend(path for path in FILES if not (ROOT / path).is_file())
    for package in DIRECTORIES["backend/app"]:
        path = f"backend/app/{package}/__init__.py"
        if not (ROOT / path).is_file():
            missing.append(path)

    if missing:
        print("Missing required paths:\n" + "\n".join(missing))
        return 1
    print("FOOTLYTICS project structure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
