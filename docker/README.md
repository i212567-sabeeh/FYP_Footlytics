# Containers

The root docker-compose.yml starts optional development Redis only. The Phase 1
API and frontend do not require Redis. API and worker images will be introduced
when processing jobs are implemented; no placeholder worker runs now.

Prefer a Linux container or WSL for the future RQ/CV worker on Windows. Verify the
selected RQ worker class and process model in that phase before documenting a
native Windows launch command. CPU processing must remain supported.
