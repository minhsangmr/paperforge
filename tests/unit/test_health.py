"""Tests for API liveness."""

from fastapi.testclient import TestClient

from paperforge.main import app


def test_liveness_endpoint() -> None:
    response = TestClient(app).get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "paperforge",
        "version": "0.1.0",
    }
