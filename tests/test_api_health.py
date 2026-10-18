"""Unit tests for FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest

from src.api.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
    assert "r4" in data["service"]


def test_audit_status_endpoint():
    response = client.get("/api/v1/audit/status")
    assert response.status_code == 200
    data = response.json()
    assert "total_files_scanned" in data or "blockers" in data
