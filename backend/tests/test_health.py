from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_endpoint(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "application": "FOOTLYTICS"}


def test_cors_allows_only_configured_origin(settings: Settings) -> None:
    settings.cors_origins = ["http://localhost:5173"]
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        rejected = client.get(
            "/api/health", headers={"Origin": "https://untrusted.example"}
        )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in rejected.headers
