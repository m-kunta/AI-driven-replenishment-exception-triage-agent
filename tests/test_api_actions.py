import pytest
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)
auth = ("admin", "password123")

@pytest.fixture(autouse=True)
def override_env(monkeypatch):
    monkeypatch.setenv("API_PASSWORD", "password123")
    monkeypatch.setenv("API_USERNAME", "admin")

def test_submit_action():
    payload = {
        "request_id": "api-req-1",
        "exception_id": "api-exc-1",
        "run_date": "2026-04-24",
        "action_type": "CREATE_REVIEW",
        "requested_by_role": "planner",
        "payload": {"test": "data"}
    }
    response = client.post("/actions", json=payload, auth=auth)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("completed", "failed", "sent")
    assert data["request_id"] == "api-req-1"
    assert data["requested_by"] == "admin"

def test_get_actions():
    response = client.get("/actions/api-exc-1", auth=auth)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["request_id"] == "api-req-1"

def test_retry_action():
    # First submit an action that fails using simulate_failure
    payload = {
        "request_id": "api-req-fail",
        "exception_id": "api-exc-2",
        "run_date": "2026-04-24",
        "action_type": "CREATE_REVIEW",
        "requested_by_role": "planner",
        "payload": {"simulate_failure": True}
    }
    res1 = client.post("/actions", json=payload, auth=auth)
    assert res1.status_code == 201
    assert res1.json()["status"] == "failed"
    
    # Now retry it
    res2 = client.post(f"/actions/api-req-fail/retry", auth=auth)
    assert res2.status_code == 200
    assert res2.json()["status"] == "failed"
