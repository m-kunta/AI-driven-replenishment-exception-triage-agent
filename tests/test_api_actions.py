import pytest
from fastapi.testclient import TestClient
from src.actions.service import ActionService
from src.api import app as api_app_module
from src.api.app import app
from src.db.action_store import ActionStore

client = TestClient(app)
auth = ("admin", "password123")

@pytest.fixture(autouse=True)
def override_env(monkeypatch, tmp_path):
    monkeypatch.setenv("API_PASSWORD", "password123")
    monkeypatch.setenv("API_USERNAME", "admin")
    monkeypatch.setenv("API_USER_ROLE", "analyst")
    monkeypatch.setenv("API_USER_ROLES", "admin:analyst,planner1:planner")
    store = ActionStore(db_path=str(tmp_path / "actions-test.db"))
    api_app_module.action_store = store
    api_app_module.action_service = ActionService(store)

def test_submit_action():
    payload = {
        "request_id": "api-req-1",
        "exception_id": "api-exc-1",
        "run_date": "2026-04-24",
        "action_type": "CREATE_REVIEW",
        "payload": {"test": "data"}
    }
    response = client.post("/actions", json=payload, auth=auth)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("completed", "failed", "sent")
    assert data["request_id"] == "api-req-1"
    assert data["requested_by"] == "admin"
    assert data["requested_by_role"] == "analyst"


def test_submit_action_ignores_client_role(monkeypatch):
    monkeypatch.setenv("API_USER_ROLES", "admin:planner,planner1:planner")
    payload = {
        "request_id": "api-req-role-1",
        "exception_id": "api-exc-role-1",
        "run_date": "2026-04-24",
        "action_type": "CREATE_REVIEW",
        "requested_by_role": "analyst",
        "payload": {"test": "data"}
    }
    response = client.post("/actions", json=payload, auth=auth)
    assert response.status_code == 201
    data = response.json()
    assert data["requested_by"] == "admin"
    assert data["requested_by_role"] == "planner"

def test_get_actions():
    seed_payload = {
        "request_id": "api-req-list-1",
        "exception_id": "api-exc-1",
        "run_date": "2026-04-24",
        "action_type": "CREATE_REVIEW",
        "payload": {"test": "data"}
    }
    seed_response = client.post("/actions", json=seed_payload, auth=auth)
    assert seed_response.status_code == 201

    response = client.get("/actions/api-exc-1", auth=auth)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["request_id"] == "api-req-list-1"

def test_retry_action():
    # First submit an action that fails using simulate_failure
    payload = {
        "request_id": "api-req-fail",
        "exception_id": "api-exc-2",
        "run_date": "2026-04-24",
        "action_type": "CREATE_REVIEW",
        "payload": {"simulate_failure": True}
    }
    res1 = client.post("/actions", json=payload, auth=auth)
    assert res1.status_code == 201
    assert res1.json()["status"] == "failed"
    
    # Now retry it
    res2 = client.post(f"/actions/api-req-fail/retry", auth=auth)
    assert res2.status_code == 200
    assert res2.json()["status"] == "failed"


@pytest.mark.parametrize(
    ("request_id", "action_type"),
    [
        ("api-req-forbidden-store-check", "STORE_CHECK"),
        ("api-req-forbidden-vendor-follow-up", "VENDOR_FOLLOW_UP"),
    ],
)
def test_submit_action_rejects_planner_only_action_for_analyst(request_id, action_type):
    payload = {
        "request_id": request_id,
        "exception_id": f"{request_id}-exc",
        "run_date": "2026-04-24",
        "action_type": action_type,
        "payload": {"notes": "Planner-only follow-up"},
    }
    response = client.post("/actions", json=payload, auth=auth)
    assert response.status_code == 403
    assert "requires planner role" in response.json()["detail"]


@pytest.mark.parametrize(
    ("request_id", "action_type"),
    [
        ("api-req-planner-store-check", "STORE_CHECK"),
        ("api-req-planner-vendor-follow-up", "VENDOR_FOLLOW_UP"),
    ],
)
def test_submit_action_resolves_role_from_authenticated_username(request_id, action_type):
    planner_auth = ("planner1", "password123")
    payload = {
        "request_id": request_id,
        "exception_id": f"{request_id}-exc",
        "run_date": "2026-04-24",
        "action_type": action_type,
        "payload": {"notes": "Planner-only follow-up"},
    }

    response = client.post("/actions", json=payload, auth=planner_auth)

    assert response.status_code == 201
    data = response.json()
    assert data["requested_by"] == "planner1"
    assert data["requested_by_role"] == "planner"


def test_get_current_user_profile_returns_resolved_role():
    response = client.get("/me", auth=("planner1", "password123"))

    assert response.status_code == 200
    assert response.json() == {
        "username": "planner1",
        "role": "planner",
    }
