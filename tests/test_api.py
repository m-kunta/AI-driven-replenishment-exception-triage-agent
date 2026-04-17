from unittest.mock import patch, mock_open

import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)

valid_auth = ("admin", "secret123")
invalid_auth = ("admin", "wrong_password")


@pytest.fixture(autouse=True)
def _api_credentials(monkeypatch):
    """Scoped credential injection — prevents module-level env var leakage."""
    monkeypatch.setenv("API_USERNAME", "admin")
    monkeypatch.setenv("API_PASSWORD", "secret123")


def test_health_check():
    """Test health endpoint requires no auth."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "triage_api"}


def test_get_queue_unauthorized():
    """Test endpoints reject missing or invalid auth."""
    # Missing auth
    response = client.get("/exceptions/queue/CRITICAL/2026-04-11")
    assert response.status_code == 401

    # Invalid auth
    response = client.get("/exceptions/queue/CRITICAL/2026-04-11", auth=invalid_auth)
    assert response.status_code == 401


def test_get_queue_invalid_priority():
    """Test 400 bad request on invalid priority string."""
    response = client.get("/exceptions/queue/INVALID/2026-04-11", auth=valid_auth)
    assert response.status_code == 400
    assert "Invalid priority level" in response.json()["detail"]


@patch("src.api.app.Path.exists")
def test_get_queue_not_found(mock_exists):
    """Test 404 when queue file does not exist."""
    mock_exists.return_value = False
    response = client.get("/exceptions/queue/HIGH/2026-04-11", auth=valid_auth)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@patch("src.api.app.Path.exists")
def test_get_queue_success(mock_exists):
    """Test valid retrieval mocks file open."""
    mock_exists.return_value = True
    fake_json = '[{"id": "exc_001", "priority": "HIGH"}]'
    
    with patch("src.api.app.open", mock_open(read_data=fake_json)):
        response = client.get("/exceptions/queue/HIGH/2026-04-11", auth=valid_auth)
        
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "exc_001"


@patch("src.api.app.BackgroundTasks.add_task")
def test_trigger_pipeline(mock_add_task):
    """Test that the pipeline trigger accepts payload and queues background task."""
    payload = {
        "run_date": "2026-04-16",
        "sample": True,
        "no_alerts": True,
        "dry_run": False
    }
    response = client.post("/pipeline/trigger", json=payload, auth=valid_auth)
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["params"]["run_date"] == "2026-04-16"
    assert mock_add_task.called
