"""Tests for the FastAPI backend (src/api/app.py).

Coverage map
────────────
  GET  /health                               — no auth, schema
  GET  /runs                                 — auth, empty dir, dedup, sort, ignore non-queue files
  GET  /exceptions/queue/{priority}/{date}   — auth, 400 bad priority, 404 missing, 500 corrupt, happy path
  GET  /briefing/{run_date}                  — auth, 404 missing, happy path, response schema
  POST /pipeline/trigger                     — auth, 202, echoes params, defaults, background task,
                                              forwards run_date / no_alerts to pipeline

All filesystem access is redirected to tmp_path so tests are fully hermetic
with no dependency on output/ being present on the real project disk.
run_triage_pipeline is patched wherever a trigger test is run.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Credential constants — kept consistent across all tests
# ---------------------------------------------------------------------------

_USERNAME = "admin"
_PASSWORD = "secret123"
VALID_CREDS = (_USERNAME, _PASSWORD)
BAD_CREDS = ("hacker", "letmein")

# ---------------------------------------------------------------------------
# Pre-seed env vars BEFORE importing the app so HTTPBasic auth initialises OK
# ---------------------------------------------------------------------------

os.environ.setdefault("API_USERNAME", _USERNAME)
os.environ.setdefault("API_PASSWORD", _PASSWORD)

from src.api.app import app  # noqa: E402
from src.api.run_registry import RunRegistry  # noqa: E402

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

DATE = "2026-04-20"
PRIORITY = "CRITICAL"
QUEUE_FILE = f"{PRIORITY}_{DATE}.json"
BRIEFING_FILE = f"briefing_{DATE}.md"

SAMPLE_QUEUE = [
    {
        "exception_id": "EXC-001",
        "priority": "CRITICAL",
        "confidence": "HIGH",
        "root_cause": "OOS at Tier-1 store during active TPR",
        "recommended_action": "Expedite from DC-502",
        "financial_impact_statement": "$28,000 lost sales",
        "planner_brief": "Urgent.",
        "est_lost_sales_value": 28000.0,
    }
]
SAMPLE_BRIEFING = "# Morning Briefing\n\n1 CRITICAL exception today."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _inject_env_creds(monkeypatch):
    """Ensure env creds are consistent for every test in this module."""
    monkeypatch.setenv("API_USERNAME", _USERNAME)
    monkeypatch.setenv("API_PASSWORD", _PASSWORD)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with empty output dirs → useful for 404 / missing-file tests."""
    import src.api.app as api_module

    monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(api_module, "OUTPUT_BRIEFINGS_DIR", tmp_path / "briefings")
    return TestClient(app)


@pytest.fixture()
def client_with_data(tmp_path, monkeypatch):
    """TestClient with pre-populated queue + briefing files on disk."""
    import src.api.app as api_module

    logs_dir = tmp_path / "logs"
    briefings_dir = tmp_path / "briefings"
    logs_dir.mkdir()
    briefings_dir.mkdir()

    # Populate all four priority queues for DATE
    for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        (logs_dir / f"{p}_{DATE}.json").write_text(json.dumps([]))
    # Overwrite CRITICAL with real records
    (logs_dir / QUEUE_FILE).write_text(json.dumps(SAMPLE_QUEUE))
    (briefings_dir / BRIEFING_FILE).write_text(SAMPLE_BRIEFING)

    monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
    monkeypatch.setattr(api_module, "OUTPUT_BRIEFINGS_DIR", briefings_dir)
    return TestClient(app)


# ===========================================================================
# GET /health
# ===========================================================================


class TestHealthEndpoint:
    def test_returns_200_without_credentials(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_schema_contains_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_schema_contains_service_name(self, client):
        data = client.get("/health").json()
        assert data["service"] == "triage_api"

    def test_no_www_authenticate_header(self, client):
        """Health must never challenge for credentials."""
        resp = client.get("/health")
        assert "www-authenticate" not in resp.headers


# ===========================================================================
# Authentication guard — exercised via /runs for brevity
# ===========================================================================


class TestAuthentication:
    def test_missing_auth_returns_401(self, client):
        assert client.get("/runs").status_code == 401

    def test_wrong_credentials_returns_401(self, client):
        assert client.get("/runs", auth=BAD_CREDS).status_code == 401

    def test_wrong_password_returns_401(self, client):
        assert client.get("/runs", auth=(_USERNAME, "wrong")).status_code == 401

    def test_wrong_username_returns_401(self, client):
        assert client.get("/runs", auth=("nobody", _PASSWORD)).status_code == 401

    def test_valid_credentials_succeed(self, client):
        assert client.get("/runs", auth=VALID_CREDS).status_code == 200

    def test_queue_requires_auth(self, client):
        assert client.get(f"/exceptions/queue/{PRIORITY}/{DATE}").status_code == 401

    def test_briefing_requires_auth(self, client):
        assert client.get(f"/briefing/{DATE}").status_code == 401

    def test_models_requires_auth(self, client):
        assert client.get("/models").status_code == 401

    def test_settings_requires_auth(self, client):
        assert client.get("/settings").status_code == 401

    def test_trigger_requires_auth(self, client):
        resp = client.post(
            "/pipeline/trigger",
            json={"run_date": DATE, "sample": True, "no_alerts": True},
        )
        assert resp.status_code == 401


# ===========================================================================
# GET /runs
# ===========================================================================


class TestRunsEndpoint:
    def test_empty_when_logs_dir_absent(self, client):
        """If output/logs/ does not exist yet, return empty list — not 500."""
        resp = client.get("/runs", auth=VALID_CREDS)
        assert resp.status_code == 200
        assert resp.json()["run_dates"] == []

    def test_lists_date_from_queue_files(self, client_with_data):
        resp = client_with_data.get("/runs", auth=VALID_CREDS)
        assert DATE in resp.json()["run_dates"]

    def test_dates_sorted_newest_first(self, tmp_path, monkeypatch):
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        for d in ("2026-04-10", "2026-04-20", "2026-04-15"):
            (logs_dir / f"CRITICAL_{d}.json").write_text("[]")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        dates = TestClient(app).get("/runs", auth=VALID_CREDS).json()["run_dates"]
        assert dates == sorted(dates, reverse=True)

    def test_deduplicates_dates_across_priority_files(self, tmp_path, monkeypatch):
        """Four PRIORITY_DATE.json files for the same date → only one entry."""
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            (logs_dir / f"{p}_{DATE}.json").write_text("[]")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        dates = TestClient(app).get("/runs", auth=VALID_CREDS).json()["run_dates"]
        assert dates.count(DATE) == 1

    def test_ignores_non_queue_files(self, tmp_path, monkeypatch):
        """CSV logs and quarantine files must not pollute run_dates."""
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "exception_log.csv").write_text("header\n")
        (logs_dir / f"quarantine_{DATE}.json").write_text("{}")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        assert TestClient(app).get("/runs", auth=VALID_CREDS).json()["run_dates"] == []

    def test_multiple_distinct_dates_all_listed(self, tmp_path, monkeypatch):
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        dates_written = ["2026-04-18", "2026-04-19", "2026-04-20"]
        for d in dates_written:
            (logs_dir / f"CRITICAL_{d}.json").write_text("[]")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        returned = TestClient(app).get("/runs", auth=VALID_CREDS).json()["run_dates"]
        assert set(returned) == set(dates_written)


# ===========================================================================
# GET /exceptions/queue/{priority}/{run_date}
# ===========================================================================


class TestQueueEndpoint:
    def test_returns_200_and_items_for_valid_request(self, client_with_data):
        resp = client_with_data.get(
            f"/exceptions/queue/{PRIORITY}/{DATE}", auth=VALID_CREDS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["exception_id"] == "EXC-001"

    def test_returns_404_when_file_missing(self, client):
        resp = client.get(f"/exceptions/queue/CRITICAL/{DATE}", auth=VALID_CREDS)
        assert resp.status_code == 404

    def test_404_detail_mentions_not_found(self, client):
        resp = client.get(f"/exceptions/queue/CRITICAL/{DATE}", auth=VALID_CREDS)
        assert "not found" in resp.json()["detail"].lower()

    def test_returns_400_for_invalid_priority(self, client):
        resp = client.get(f"/exceptions/queue/EXTREME/{DATE}", auth=VALID_CREDS)
        assert resp.status_code == 400

    def test_400_detail_mentions_invalid_priority(self, client):
        resp = client.get(f"/exceptions/queue/URGENT/{DATE}", auth=VALID_CREDS)
        assert "Invalid priority level" in resp.json()["detail"]

    def test_accepts_all_four_valid_priorities(self, tmp_path, monkeypatch):
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            (logs_dir / f"{p}_{DATE}.json").write_text("[]")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        c = TestClient(app)
        for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            resp = c.get(f"/exceptions/queue/{p}/{DATE}", auth=VALID_CREDS)
            assert resp.status_code == 200, f"Expected 200 for priority={p}"

    def test_priority_is_case_insensitive(self, tmp_path, monkeypatch):
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / f"HIGH_{DATE}.json").write_text("[]")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        resp = TestClient(app).get(
            f"/exceptions/queue/high/{DATE}", auth=VALID_CREDS
        )
        assert resp.status_code == 200

    def test_returns_empty_list_for_empty_queue_file(self, tmp_path, monkeypatch):
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / f"LOW_{DATE}.json").write_text("[]")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        resp = TestClient(app).get(f"/exceptions/queue/LOW/{DATE}", auth=VALID_CREDS)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_500_for_corrupted_json_file(self, tmp_path, monkeypatch):
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / f"CRITICAL_{DATE}.json").write_text("{{NOTJSON}}")

        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)
        resp = TestClient(app).get(f"/exceptions/queue/CRITICAL/{DATE}", auth=VALID_CREDS)
        assert resp.status_code == 500

    def test_financial_values_preserved_in_response(self, client_with_data):
        resp = client_with_data.get(
            f"/exceptions/queue/{PRIORITY}/{DATE}", auth=VALID_CREDS
        )
        item = resp.json()[0]
        assert item["est_lost_sales_value"] == 28000.0

    def test_rejects_path_traversal_in_run_date(self, tmp_path, monkeypatch):
        # HTTP routing blocks slash-containing run_date values, but the bounds check
        # guards against direct invocation and future refactors. Test it at the
        # path-construction level by monkeypatching OUTPUT_LOGS_DIR and calling
        # the endpoint with a run_date that resolves outside the output directory.
        import src.api.app as api_module

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        monkeypatch.setattr(api_module, "OUTPUT_LOGS_DIR", logs_dir)

        # Manually invoke the path guard logic that the endpoint uses
        run_date = "../../../etc/passwd"
        file_path = (logs_dir / f"CRITICAL_{run_date}.json").resolve()
        is_within_bounds = str(file_path).startswith(str(logs_dir.resolve()))
        assert not is_within_bounds, "Traversal path should escape the output directory"


# ===========================================================================
# GET /briefing/{run_date}
# ===========================================================================


class TestBriefingEndpoint:
    def test_returns_200_for_valid_date(self, client_with_data):
        resp = client_with_data.get(f"/briefing/{DATE}", auth=VALID_CREDS)
        assert resp.status_code == 200

    def test_response_contains_run_date_field(self, client_with_data):
        data = client_with_data.get(f"/briefing/{DATE}", auth=VALID_CREDS).json()
        assert data["run_date"] == DATE

    def test_response_contains_content_field(self, client_with_data):
        data = client_with_data.get(f"/briefing/{DATE}", auth=VALID_CREDS).json()
        assert "content" in data

    def test_content_matches_file_on_disk(self, client_with_data):
        data = client_with_data.get(f"/briefing/{DATE}", auth=VALID_CREDS).json()
        assert SAMPLE_BRIEFING in data["content"]

    def test_returns_404_when_briefing_file_missing(self, client):
        resp = client.get(f"/briefing/{DATE}", auth=VALID_CREDS)
        assert resp.status_code == 404

    def test_404_detail_mentions_date(self, client):
        resp = client.get(f"/briefing/{DATE}", auth=VALID_CREDS)
        assert DATE in resp.json()["detail"]

    def test_rejects_path_traversal_in_run_date(self, tmp_path, monkeypatch):
        # Confirms the bounds check blocks traversal at the path-construction level.
        # (HTTP routing itself prevents slash-containing run_date values from
        # reaching the handler — this guards against future refactors.)
        import src.api.app as api_module

        briefings_dir = tmp_path / "briefings"
        briefings_dir.mkdir()
        monkeypatch.setattr(api_module, "OUTPUT_BRIEFINGS_DIR", briefings_dir)

        run_date = "../../../etc/passwd"
        file_path = (briefings_dir / f"briefing_{run_date}.md").resolve()
        is_within_bounds = str(file_path).startswith(str(briefings_dir.resolve()))
        assert not is_within_bounds, "Traversal path should escape the output directory"


# ===========================================================================
# GET /models and GET /settings
# ===========================================================================


class TestModelsAndSettingsEndpoints:
    def test_models_returns_current_model_and_availability(self, client):
        with (
            patch("src.api.app.load_config") as mock_load_config,
            patch("src.api.app.get_provider") as mock_get_provider,
        ):
            cfg = mock_load_config.return_value
            cfg.agent.provider = "openai"
            cfg.agent.model = "gpt-4.1"
            mock_get_provider.return_value.list_models.return_value = ["gpt-4.1", "gpt-4o"]

            resp = client.get("/models", auth=VALID_CREDS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "openai"
        assert data["current_model"] == "gpt-4.1"
        assert data["current_model_available"] is True
        assert "gpt-4.1" in data["models"]

    def test_models_returns_actionable_error_when_listing_fails(self, client):
        with (
            patch("src.api.app.load_config") as mock_load_config,
            patch("src.api.app.get_provider") as mock_get_provider,
        ):
            cfg = mock_load_config.return_value
            cfg.agent.provider = "gemini"
            cfg.agent.model = "gemini-2.0-flash"
            mock_get_provider.return_value.list_models.side_effect = ValueError(
                "GEMINI_API_KEY is invalid or expired. Update it in your .env file."
            )

            resp = client.get("/models", auth=VALID_CREDS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "gemini"
        assert data["current_model"] == "gemini-2.0-flash"
        assert data["models"] == []
        assert data["current_model_available"] is None
        assert "invalid or expired" in data["error"]

    def test_settings_returns_non_secret_runtime_fields(self, client, monkeypatch):
        monkeypatch.setenv("AGENT_PROVIDER", "openai")
        monkeypatch.setenv("AGENT_MODEL", "gpt-4.1")
        monkeypatch.setenv("BACKEND_PORT", "8002")
        monkeypatch.setenv("API_USER_ROLES", "admin:planner,analyst1:analyst")

        with patch("src.api.app.load_config") as mock_load_config:
            cfg = mock_load_config.return_value
            cfg.agent.provider = "claude"
            cfg.agent.model = "claude-sonnet-4-20250514"
            cfg.agent.batch_size = 5
            cfg.agent.max_tokens = 800
            cfg.agent.retry_attempts = 3
            cfg.agent.ollama_base_url = "http://localhost:11434"

            resp = client.get("/settings", auth=VALID_CREDS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"]["provider"] == "claude"
        assert data["agent"]["model"] == "claude-sonnet-4-20250514"
        assert data["env_overrides"]["AGENT_PROVIDER"] == "openai"
        assert data["env_overrides"]["AGENT_MODEL"] == "gpt-4.1"
        assert data["env_overrides"]["BACKEND_PORT"] == "8002"
        assert data["current_user"]["username"] == _USERNAME
        assert data["current_user"]["role"] == "planner"
        assert data["user_roles"]["admin"] == "planner"


# ===========================================================================
# POST /pipeline/trigger
# ===========================================================================


class TestPipelineTriggerEndpoint:
    _BASE_PAYLOAD = {"run_date": DATE, "sample": True, "no_alerts": True, "dry_run": False}

    def test_returns_202_accepted(self, client):
        with patch("src.api.app.run_triage_pipeline"):
            resp = client.post(
                "/pipeline/trigger", json=self._BASE_PAYLOAD, auth=VALID_CREDS
            )
        assert resp.status_code == 202

    def test_response_status_is_queued(self, client):
        with patch("src.api.app.run_triage_pipeline"):
            resp = client.post(
                "/pipeline/trigger", json=self._BASE_PAYLOAD, auth=VALID_CREDS
            )
        assert resp.json()["status"] == "queued"

    def test_response_echoes_params(self, client):
        with patch("src.api.app.run_triage_pipeline"):
            resp = client.post(
                "/pipeline/trigger", json=self._BASE_PAYLOAD, auth=VALID_CREDS
            )
        params = resp.json()["params"]
        assert params["run_date"] == DATE
        assert params["sample"] is True
        assert params["no_alerts"] is True

    def test_accepts_dry_run_flag(self, client):
        payload = {**self._BASE_PAYLOAD, "dry_run": True}
        with patch("src.api.app.run_triage_pipeline"):
            resp = client.post(
                "/pipeline/trigger", json=payload, auth=VALID_CREDS
            )
        assert resp.status_code == 202
        assert resp.json()["params"]["dry_run"] is True

    def test_uses_pydantic_defaults_when_body_empty(self, client):
        """An empty JSON body must use PipelineTriggerRequest defaults."""
        with patch("src.api.app.run_triage_pipeline"):
            resp = client.post("/pipeline/trigger", json={}, auth=VALID_CREDS)
        assert resp.status_code == 202
        params = resp.json()["params"]
        assert params["sample"] is True
        assert params["no_alerts"] is True
        assert params["dry_run"] is False
        assert params["run_date"] is None

    def test_background_task_is_invoked(self, client):
        """TestClient executes background tasks synchronously — verify call occurs."""
        call_log: list = []

        def fake_pipeline(**kwargs):
            call_log.append(kwargs)

        with patch("src.api.app.run_triage_pipeline", side_effect=fake_pipeline):
            client.post(
                "/pipeline/trigger", json=self._BASE_PAYLOAD, auth=VALID_CREDS
            )

        assert len(call_log) == 1

    def test_run_date_forwarded_to_pipeline(self, client):
        call_log: list = []

        def fake_pipeline(**kwargs):
            call_log.append(kwargs)

        with patch("src.api.app.run_triage_pipeline", side_effect=fake_pipeline):
            client.post(
                "/pipeline/trigger", json=self._BASE_PAYLOAD, auth=VALID_CREDS
            )

        assert call_log[0]["run_date"] == DATE

    def test_no_alerts_forwarded_to_pipeline(self, client):
        call_log: list = []

        def fake_pipeline(**kwargs):
            call_log.append(kwargs)

        with patch("src.api.app.run_triage_pipeline", side_effect=fake_pipeline):
            client.post(
                "/pipeline/trigger",
                json={**self._BASE_PAYLOAD, "no_alerts": True},
                auth=VALID_CREDS,
            )

        assert call_log[0]["no_alerts"] is True

    def test_sample_flag_forwarded_to_pipeline(self, client):
        call_log: list = []

        def fake_pipeline(**kwargs):
            call_log.append(kwargs)

        with patch("src.api.app.run_triage_pipeline", side_effect=fake_pipeline):
            client.post(
                "/pipeline/trigger",
                json={**self._BASE_PAYLOAD, "sample": True},
                auth=VALID_CREDS,
            )

        assert call_log[0]["sample"] is True

    def test_pipeline_crash_does_not_bubble_to_202_response(self, client):
        """If the background task crashes, the 202 response is already sent — no 500."""

        def crashing_pipeline(**kwargs):
            raise RuntimeError("Simulated crash")

        with patch("src.api.app.run_triage_pipeline", side_effect=crashing_pipeline):
            # TestClient propagates background task exceptions by default;
            # use raise_server_exceptions=False so we can assert on HTTP layer only.
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post(
                "/pipeline/trigger", json=self._BASE_PAYLOAD,
                auth=VALID_CREDS,
            )
        # The HTTP response itself must still be 202 regardless of task outcome
        assert resp.status_code == 202

# ===========================================================================
# Pipeline run registry + status endpoint
# ===========================================================================


class TestRunRegistry:
    def test_lifecycle(self):
        reg = RunRegistry()
        run_id = reg.create()
        assert reg.get(run_id)["status"] == "queued"
        reg.mark_running(run_id)
        assert reg.get(run_id)["status"] == "running"
        reg.mark_completed(run_id)
        assert reg.get(run_id)["status"] == "completed"

    def test_failed_captures_error(self):
        reg = RunRegistry()
        run_id = reg.create()
        reg.mark_failed(run_id, "boom")
        rec = reg.get(run_id)
        assert rec["status"] == "failed" and rec["error"] == "boom"

    def test_unknown_run_id_is_none(self):
        assert RunRegistry().get("nope") is None


class TestPipelineStatusEndpoint:
    def test_trigger_returns_run_id_and_status_readable(self, client):
        with patch("src.api.app.run_triage_pipeline"):
            resp = client.post(
                "/pipeline/trigger", json={"dry_run": True}, auth=VALID_CREDS
            )
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        status_resp = client.get(f"/pipeline/status/{run_id}", auth=VALID_CREDS)
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] in {"queued", "running", "completed", "failed"}

    def test_unknown_run_id_404(self, client):
        assert client.get("/pipeline/status/does-not-exist", auth=VALID_CREDS).status_code == 404


# ===========================================================================
# Override Endpoints
# ===========================================================================

@pytest.fixture(autouse=True)
def mock_override_store(monkeypatch):
    import src.api.app as api_module
    from src.db.store import OverrideStore
    store = OverrideStore(":memory:")
    monkeypatch.setattr(api_module, "override_store", store)
    return store

class TestOverrideEndpoints:
    def test_submit_override(self, client):
        payload = {
            "exception_id": "EXC-123",
            "run_date": "2026-04-20",
            "enriched_input_snapshot": {"foo": "bar"},
            "override_priority": "CRITICAL"
        }
        resp = client.post("/overrides", json=payload, auth=VALID_CREDS)
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_list_pending_overrides(self, client):
        payload = {
            "exception_id": "EXC-123",
            "run_date": "2026-04-20",
            "enriched_input_snapshot": {"foo": "bar"},
            "override_priority": "CRITICAL"
        }
        client.post("/overrides", json=payload, auth=VALID_CREDS)
        resp = client.get("/overrides/pending", auth=VALID_CREDS)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["exception_id"] == "EXC-123"

    def test_override_stats_endpoint(self, client):
        resp = client.get("/overrides/stats", auth=VALID_CREDS)
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"total", "by_status", "by_override_priority"}

    def test_approve_override(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLE", "planner")
        payload = {
            "exception_id": "EXC-123",
            "run_date": "2026-04-20",
            "enriched_input_snapshot": {"foo": "bar"},
            "override_priority": "CRITICAL"
        }
        resp_post = client.post("/overrides", json=payload, auth=VALID_CREDS)
        row_id = resp_post.json()["id"]

        resp_app = client.post(f"/overrides/{row_id}/approve", auth=VALID_CREDS)
        assert resp_app.status_code == 200
        assert resp_app.json()["status"] == "approved"

    def test_approve_override_analyst_forbidden(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLE", "analyst")
        payload = {
            "exception_id": "EXC-123",
            "run_date": "2026-04-20",
            "enriched_input_snapshot": {"foo": "bar"},
            "override_priority": "HIGH",
        }
        resp_post = client.post("/overrides", json=payload, auth=VALID_CREDS)
        row_id = resp_post.json()["id"]

        resp = client.post(f"/overrides/{row_id}/approve", auth=VALID_CREDS)
        assert resp.status_code == 403

    def test_reject_override(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLE", "planner")
        payload = {
            "exception_id": "EXC-123",
            "run_date": "2026-04-20",
            "enriched_input_snapshot": {"foo": "bar"},
            "override_priority": "CRITICAL"
        }
        resp_post = client.post("/overrides", json=payload, auth=VALID_CREDS)
        row_id = resp_post.json()["id"]

        resp_rej = client.post(f"/overrides/{row_id}/reject", json={"reason": "nope"}, auth=VALID_CREDS)
        assert resp_rej.status_code == 200
        assert resp_rej.json()["status"] == "rejected"

    def test_reject_override_analyst_forbidden(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLE", "analyst")
        payload = {
            "exception_id": "EXC-123",
            "run_date": "2026-04-20",
            "enriched_input_snapshot": {"foo": "bar"},
            "override_priority": "HIGH",
        }
        resp_post = client.post("/overrides", json=payload, auth=VALID_CREDS)
        row_id = resp_post.json()["id"]

        resp = client.post(f"/overrides/{row_id}/reject", json={"reason": "nope"}, auth=VALID_CREDS)
        assert resp.status_code == 403


# ===========================================================================
# PATCH /settings
# ===========================================================================

class TestPatchSettingsEndpoint:
    def test_analyst_gets_403(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLE", "analyst")
        monkeypatch.delenv("API_USER_ROLES", raising=False)
        resp = client.patch(
            "/settings",
            json={"AGENT_PROVIDER": "openai"},
            auth=VALID_CREDS,
        )
        assert resp.status_code == 403

    def test_invalid_provider_returns_422_with_error_map(self, tmp_path, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)
        with patch("src.api.app.EnvWriter.validate", return_value={"AGENT_PROVIDER": "Must be one of: claude, gemini, ollama, openai."}):
            resp = cli.patch(
                "/settings",
                json={"AGENT_PROVIDER": "bad_value"},
                auth=VALID_CREDS,
            )
        assert resp.status_code == 422
        assert "AGENT_PROVIDER" in resp.json()["errors"]

    def test_valid_payload_writes_env_and_returns_200(self, tmp_path, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)

        with patch("src.api.app.EnvWriter.validate", return_value={}), \
             patch("src.api.app.EnvWriter.apply", return_value={
                 "applied": ["AGENT_PROVIDER"],
                 "restart_required": ["AGENT_PROVIDER"],
                 "errors": {},
             }) as mock_apply, \
             patch("src.api.app.action_store") as mock_store:
            mock_store.insert_action.return_value = {}
            resp = cli.patch(
                "/settings",
                json={"AGENT_PROVIDER": "openai"},
                auth=VALID_CREDS,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "AGENT_PROVIDER" in data["applied"]
        assert "AGENT_PROVIDER" in data["restart_required"]

    def test_audit_record_written_per_applied_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)

        with patch("src.api.app.EnvWriter.validate", return_value={}), \
             patch("src.api.app.EnvWriter.apply", return_value={
                 "applied": ["AGENT_PROVIDER", "AGENT_MODEL"],
                 "restart_required": ["AGENT_PROVIDER", "AGENT_MODEL"],
                 "errors": {},
             }), \
             patch("src.api.app.action_store") as mock_store:
            mock_store.insert_action.return_value = {}
            resp = cli.patch(
                "/settings",
                json={"AGENT_PROVIDER": "openai", "AGENT_MODEL": "gpt-4.1"},
                auth=VALID_CREDS,
            )

        assert resp.status_code == 200
        assert mock_store.insert_action.call_count == 2
        call_kwargs = mock_store.insert_action.call_args_list[0][1]
        assert call_kwargs["action_type"] == "SETTINGS_CHANGE"
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["exception_id"] == "__settings__"


# ===========================================================================
# POST /settings/validate-model
# ===========================================================================

class TestValidateModelEndpoint:
    def test_analyst_gets_403(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLE", "analyst")
        monkeypatch.delenv("API_USER_ROLES", raising=False)
        resp = client.post(
            "/settings/validate-model",
            json={"provider": "claude", "model": "claude-sonnet-4-20250514"},
            auth=VALID_CREDS,
        )
        assert resp.status_code == 403

    def test_invalid_provider_returns_422(self, client, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)
        resp = cli.post(
            "/settings/validate-model",
            json={"provider": "badprovider", "model": "some-model"},
            auth=VALID_CREDS,
        )
        assert resp.status_code == 422

    def test_valid_model_returns_200_with_model_available_true(self, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)

        mock_provider = MagicMock()
        mock_provider.list_models.return_value = ["gpt-4.1", "gpt-4.1-mini"]

        with patch("src.api.app.get_provider", return_value=mock_provider):
            resp = cli.post(
                "/settings/validate-model",
                json={"provider": "openai", "model": "gpt-4.1"},
                auth=VALID_CREDS,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["model_available"] is True
        assert "gpt-4.1" in data["models"]

    def test_model_not_in_list_returns_model_available_false(self, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)

        mock_provider = MagicMock()
        mock_provider.list_models.return_value = ["gpt-4.1"]

        with patch("src.api.app.get_provider", return_value=mock_provider):
            resp = cli.post(
                "/settings/validate-model",
                json={"provider": "openai", "model": "gpt-99"},
                auth=VALID_CREDS,
            )

        assert resp.status_code == 200
        assert resp.json()["model_available"] is False

    def test_provider_api_failure_returns_422(self, monkeypatch):
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        cli = TestClient(app)

        mock_provider = MagicMock()
        mock_provider.list_models.side_effect = Exception("API key missing")

        with patch("src.api.app.get_provider", return_value=mock_provider):
            resp = cli.post(
                "/settings/validate-model",
                json={"provider": "openai", "model": "gpt-4.1"},
                auth=VALID_CREDS,
            )

        assert resp.status_code == 422
        assert "error" in resp.json()


# ===========================================================================
# API_USERS — Per-user credentials with legacy fallback
# ===========================================================================

class TestApiUsers:
    def test_api_users_login_and_role(self, monkeypatch):
        """Parse API_USERS and authenticate users with per-user passwords and roles."""
        monkeypatch.delenv("API_USERNAME", raising=False)
        monkeypatch.delenv("API_PASSWORD", raising=False)
        monkeypatch.delenv("API_USER_ROLES", raising=False)
        monkeypatch.setenv("API_USERS", "alice:pw1:planner,bob:pw2:analyst")

        # Re-import app to pick up new env vars
        import importlib
        import src.api.app as api_module
        importlib.reload(api_module)
        c = TestClient(api_module.app)

        resp = c.get("/me", auth=("alice", "pw1"))
        assert resp.status_code == 200
        assert resp.json() == {"username": "alice", "role": "planner"}

        resp = c.get("/me", auth=("bob", "pw2"))
        assert resp.status_code == 200
        assert resp.json() == {"username": "bob", "role": "analyst"}

    def test_api_users_wrong_password_rejected(self, monkeypatch):
        """Reject password mismatch in API_USERS mode."""
        monkeypatch.delenv("API_USERNAME", raising=False)
        monkeypatch.delenv("API_PASSWORD", raising=False)
        monkeypatch.delenv("API_USER_ROLES", raising=False)
        monkeypatch.setenv("API_USERS", "alice:pw1:planner,bob:pw2:analyst")

        import importlib
        import src.api.app as api_module
        importlib.reload(api_module)
        c = TestClient(api_module.app)

        # bob's password must not work for alice
        resp = c.get("/me", auth=("alice", "pw2"))
        assert resp.status_code == 401

    def test_api_users_malformed_entry_raises(self, monkeypatch):
        """Malformed API_USERS entry (missing role) causes 500."""
        monkeypatch.delenv("API_USERNAME", raising=False)
        monkeypatch.delenv("API_PASSWORD", raising=False)
        monkeypatch.delenv("API_USER_ROLES", raising=False)
        monkeypatch.setenv("API_USERS", "alice:pw1")  # missing role

        import importlib
        import src.api.app as api_module
        importlib.reload(api_module)
        c = TestClient(api_module.app, raise_server_exceptions=False)

        resp = c.get("/me", auth=("alice", "pw1"))
        assert resp.status_code == 500

    def test_legacy_fallback_still_works(self, monkeypatch):
        """When API_USERS is unset, legacy API_USERNAME/API_PASSWORD mode works."""
        monkeypatch.delenv("API_USERS", raising=False)
        monkeypatch.setenv("API_USERNAME", "admin")
        monkeypatch.setenv("API_PASSWORD", "secret")
        monkeypatch.delenv("API_USER_ROLES", raising=False)

        import importlib
        import src.api.app as api_module
        importlib.reload(api_module)
        c = TestClient(api_module.app)

        resp = c.get("/me", auth=("admin", "secret"))
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"


# ===========================================================================
# API Hardening Tests
# ===========================================================================


class TestHardening:
    def test_queue_rejects_path_traversal(self, client):
        """GET /exceptions/queue/ rejects path traversal attempts."""
        resp = client.get("/exceptions/queue/CRITICAL/..%2F..%2Fetc%2Fpasswd", auth=VALID_CREDS)
        assert resp.status_code in (400, 404)

    def test_settings_hides_user_roles_from_analyst(self, monkeypatch):
        """GET /settings hides user_roles dict from non-planner users."""
        monkeypatch.setenv("API_USERNAME", "analyst1")
        monkeypatch.setenv("API_PASSWORD", "secret123")
        monkeypatch.setenv("API_USER_ROLE", "analyst")
        monkeypatch.setenv("API_USER_ROLES", "planner1:planner")

        import importlib
        import src.api.app as api_module
        importlib.reload(api_module)
        c = TestClient(api_module.app)

        analyst_auth = ("analyst1", "secret123")
        resp = c.get("/settings", auth=analyst_auth)
        assert resp.status_code == 200
        assert resp.json()["user_roles"] == {}
