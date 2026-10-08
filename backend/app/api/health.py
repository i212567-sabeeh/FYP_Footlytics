from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API liveness without requiring Redis, a database or CV models."""
    return HealthResponse(status="ok", application="FOOTLYTICS")
