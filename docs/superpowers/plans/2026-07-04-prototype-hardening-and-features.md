# Prototype Hardening & Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the review findings — per-user credentials, API hardening, pipeline run status, real Slack action adapter, override analytics, Action History page, and scheduled daily runs — at prototype-appropriate weight.

**Architecture:** All backend changes live in `src/api/app.py` plus two small new modules (`run_registry.py`, a Slack adapter in `adapters.py`). Frontend gets one new page (`/actions`) and a stats strip on the planner-review page. No new services, no password hashing library, no job queue — env vars, in-memory dict, and cron.

**Tech Stack:** FastAPI, Pydantic v2, SQLite, httpx, Next.js (App Router, Tailwind), pytest.

## Global Constraints

- Python 3.9 compatible; `from __future__ import annotations` at top of every Python module.
- Loguru lazy format only in `src/` API code: `logger.error("msg: {}", e)` — never f-strings in logger calls. (`src/actions/service.py` uses stdlib `logging` — keep its existing style there.)
- All API endpoints require `Depends(get_current_username)` except `/health`.
- Never expose secret values via `/settings`, `/models`, or new endpoints.
- Backend tests: `.venv/bin/python -m pytest tests/ -v` (run from repo root; `pytest` bare is not on PATH).
- Frontend tests: run from `frontend/` — `cd frontend && npm test`.
- New general API endpoint tests go in `tests/test_api.py`; action-related tests in `tests/test_api_actions.py`.
- Frontend must only call `/api/proxy/...`, never the backend directly.
- Commit after each task.

---

### Task 1: Per-user credentials via `API_USERS`

Replace the shared-password model. New env var `API_USERS="alice:pw1:planner,bob:pw2:analyst"` (plaintext passwords — acceptable for a prototype; documented as such). Legacy `API_USERNAME`/`API_PASSWORD`/`API_USER_ROLES`/`API_USER_ROLE` keep working unchanged when `API_USERS` is unset, so nothing existing breaks.

**Files:**
- Modify: `src/api/app.py` (functions `parse_user_roles`, `get_current_username`, `get_current_user_role` — lines ~44–102)
- Modify: `.env.example` (document `API_USERS`)
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `parse_api_users() -> Dict[str, Tuple[str, str]]` mapping username → (password, role). `get_current_username` and `get_current_user_role` keep their existing signatures — later tasks rely on them unchanged.

- [ ] **Step 1: Write failing tests** (append to `tests/test_api.py`, following its existing client/env-fixture patterns):

```python
class TestApiUsers:
    def test_api_users_login_and_role(self, monkeypatch):
        monkeypatch.setenv("API_USERS", "alice:pw1:planner,bob:pw2:analyst")
        monkeypatch.setenv("API_PASSWORD", "legacy-unused")
        resp = client.get("/me", auth=("alice", "pw1"))
        assert resp.status_code == 200
        assert resp.json() == {"username": "alice", "role": "planner"}

    def test_api_users_wrong_password_rejected(self, monkeypatch):
        monkeypatch.setenv("API_USERS", "alice:pw1:planner")
        monkeypatch.setenv("API_PASSWORD", "legacy-unused")
        # bob's password must not work for alice, and vice versa
        assert client.get("/me", auth=("alice", "pw2")).status_code == 401

    def test_api_users_malformed_entry_raises(self, monkeypatch):
        monkeypatch.setenv("API_USERS", "alice:pw1")  # missing role
        monkeypatch.setenv("API_PASSWORD", "legacy-unused")
        assert client.get("/me", auth=("alice", "pw1")).status_code == 500

    def test_legacy_fallback_still_works(self, monkeypatch):
        monkeypatch.delenv("API_USERS", raising=False)
        monkeypatch.setenv("API_USERNAME", "admin")
        monkeypatch.setenv("API_PASSWORD", "secret")
        assert client.get("/me", auth=("admin", "secret")).status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_api.py::TestApiUsers -v`
Expected: FAIL (401/wrong role — `API_USERS` not parsed yet).

- [ ] **Step 3: Implement in `src/api/app.py`**

Add next to `parse_user_roles`:

```python
def parse_api_users() -> Dict[str, tuple]:
    """Parse API_USERS='user:password:role,...' into {username: (password, role)}."""
    raw = os.environ.get("API_USERS", "").strip()
    users: Dict[str, tuple] = {}
    if not raw:
        return users
    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise RuntimeError("API_USERS entries must use username:password:role format")
        username, password, role = (p.strip() for p in parts)
        role = role.lower()
        if not username or not password:
            raise RuntimeError("API_USERS entries must include a username and password")
        if role not in {"analyst", "planner"}:
            raise RuntimeError("API_USERS roles must be either 'analyst' or 'planner'")
        users[username] = (password, role)
    return users
```

Rewrite `get_current_username` to check per-user credentials first, then fall back to the legacy shared-password path:

```python
def get_current_username(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    """Verifies HTTP Basic Auth credentials from environment variables."""
    users = parse_api_users()
    if users:
        for username, (password, _role) in users.items():
            if secrets.compare_digest(credentials.username.encode("utf8"), username.encode("utf8")) and \
               secrets.compare_digest(credentials.password.encode("utf8"), password.encode("utf8")):
                return credentials.username
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Legacy shared-password mode (API_USERS unset)
    expected_username = os.environ.get("API_USERNAME", "admin")
    expected_password = os.environ.get("API_PASSWORD")
    if expected_password is None:
        raise RuntimeError("API_PASSWORD environment variable is not set")
    allowed_usernames = {expected_username, *parse_user_roles().keys()}
    is_correct_username = any(
        secrets.compare_digest(credentials.username.encode("utf8"), allowed.encode("utf8"))
        for allowed in allowed_usernames
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"), expected_password.encode("utf8")
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
```

In `get_current_user_role`, check `parse_api_users()` first:

```python
def get_current_user_role(username: str) -> str:
    """Resolve the authenticated user's role from server-side configuration."""
    users = parse_api_users()
    if username in users:
        return users[username][1]

    role = parse_user_roles().get(username)
    if role:
        return role

    role = os.environ.get("API_USER_ROLE", "analyst").strip().lower()
    if role not in {"analyst", "planner"}:
        raise RuntimeError("API_USER_ROLE must be either 'analyst' or 'planner'")
    return role
```

Add to `.env.example`:

```bash
# Per-user credentials (prototype: plaintext). When set, replaces API_USERNAME/API_PASSWORD.
# Format: username:password:role[,username:password:role...]  role ∈ analyst|planner
# API_USERS=alice:changeme1:planner,bob:changeme2:analyst
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: all PASS (new + existing legacy-auth tests).

- [ ] **Step 5: Commit**

```bash
git add src/api/app.py tests/test_api.py .env.example
git commit -m "feat: per-user credentials via API_USERS with legacy fallback"
```

---

### Task 2: API hardening — path guard, limit clamp, role-map exposure

**Files:**
- Modify: `src/api/app.py` (`get_queue` ~line 327, `get_briefing` ~line 407, `get_all_actions` ~line 526, `get_settings` ~line 179)
- Test: `tests/test_api.py` (path/settings), `tests/test_api_actions.py` (limit clamp)

**Interfaces:**
- Produces: `_resolve_output_file(base_dir: Path, file_name: str) -> Path` (raises `HTTPException(400)` on traversal). No signature changes elsewhere.

- [ ] **Step 1: Write failing tests**

In `tests/test_api.py`:

```python
class TestHardening:
    def test_queue_rejects_path_traversal(self, auth):
        resp = client.get("/exceptions/queue/CRITICAL/..%2F..%2Fetc%2Fpasswd", auth=auth)
        assert resp.status_code in (400, 404)

    def test_settings_hides_user_roles_from_analyst(self, monkeypatch, analyst_auth):
        resp = client.get("/settings", auth=analyst_auth)
        assert resp.status_code == 200
        assert resp.json()["user_roles"] == {}
```

In `tests/test_api_actions.py`:

```python
def test_get_all_actions_clamps_limit(auth):
    resp = client.get("/actions", params={"limit": 100000}, auth=auth)
    assert resp.status_code == 200  # clamped, not rejected
```

(Adapt fixture names to the file's existing auth fixtures.)

- [ ] **Step 2: Run to verify failures**

Run: `.venv/bin/python -m pytest tests/test_api.py::TestHardening tests/test_api_actions.py::test_get_all_actions_clamps_limit -v`

- [ ] **Step 3: Implement**

Add helper in `src/api/app.py`:

```python
def _resolve_output_file(base_dir: Path, file_name: str) -> Path:
    """Resolve file_name inside base_dir, rejecting any traversal outside it."""
    file_path = (base_dir / file_name).resolve()
    base = base_dir.resolve()
    try:
        file_path.relative_to(base)  # Path.is_relative_to needs 3.9+; relative_to works on 3.9
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    return file_path
```

Replace the two inline `startswith` guards:
- In `get_queue`: `file_path = _resolve_output_file(OUTPUT_LOGS_DIR, file_name)`
- In `get_briefing`: `file_path = _resolve_output_file(OUTPUT_BRIEFINGS_DIR, f"briefing_{run_date}.md")`

In `get_all_actions`, clamp at the top:

```python
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
```

In `get_settings`, only expose the role map to planners:

```python
        current_role = get_current_user_role(username)
        user_roles = parse_user_roles() if current_role == "planner" else {}
```

(and use `current_role` in the `current_user` block instead of re-resolving).

- [ ] **Step 4: Run full API tests**

Run: `.venv/bin/python -m pytest tests/test_api.py tests/test_api_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/app.py tests/test_api.py tests/test_api_actions.py
git commit -m "fix: harden path guards, clamp pagination, gate role-map exposure"
```

---

### Task 3: Pipeline run registry + status endpoint

In-memory registry (dict, thread-lock) — resets on restart, which is fine for a prototype. `POST /pipeline/trigger` returns a `run_id`; `GET /pipeline/status/{run_id}` reports `queued|running|completed|failed`.

**Files:**
- Create: `src/api/run_registry.py`
- Modify: `src/api/app.py` (`trigger_pipeline` ~line 348, new endpoint)
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `RunRegistry` with `create() -> str`, `mark_running(run_id)`, `mark_completed(run_id)`, `mark_failed(run_id, error: str)`, `get(run_id) -> Optional[dict]`. Module-level singleton `run_registry = RunRegistry()`.

- [ ] **Step 1: Write failing tests** (`tests/test_api.py`):

```python
from src.api.run_registry import RunRegistry

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
    def test_trigger_returns_run_id_and_status_readable(self, auth):
        resp = client.post("/pipeline/trigger", json={"dry_run": True}, auth=auth)
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        status_resp = client.get(f"/pipeline/status/{run_id}", auth=auth)
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] in {"queued", "running", "completed", "failed"}

    def test_unknown_run_id_404(self, auth):
        assert client.get("/pipeline/status/does-not-exist", auth=auth).status_code == 404
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError: src.api.run_registry`.

- [ ] **Step 3: Implement `src/api/run_registry.py`**

```python
"""In-memory pipeline run status registry (prototype: resets on restart)."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional


class RunRegistry:
    def __init__(self, max_entries: int = 100) -> None:
        self._runs: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def create(self) -> str:
        run_id = str(uuid.uuid4())
        with self._lock:
            if len(self._runs) >= self._max_entries:
                oldest = min(self._runs, key=lambda k: self._runs[k]["created_at"])
                del self._runs[oldest]
            self._runs[run_id] = {
                "run_id": run_id,
                "status": "queued",
                "error": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return run_id

    def _set(self, run_id: str, status: str, error: Optional[str] = None) -> None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None:
                return
            rec["status"] = status
            rec["error"] = error
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

    def mark_running(self, run_id: str) -> None:
        self._set(run_id, "running")

    def mark_completed(self, run_id: str) -> None:
        self._set(run_id, "completed")

    def mark_failed(self, run_id: str, error: str) -> None:
        self._set(run_id, "failed", error)

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._runs.get(run_id)
            return dict(rec) if rec else None


run_registry = RunRegistry()
```

In `src/api/app.py` add `from src.api.run_registry import run_registry`, then modify `trigger_pipeline`:

```python
    run_id = run_registry.create()

    def run_pipeline_task():
        logger.info("Background execution starting for API User: {}", username)
        run_registry.mark_running(run_id)
        try:
            run_triage_pipeline(
                config_path="config/config.yaml",
                run_date=payload.run_date,
                dry_run=payload.dry_run,
                no_alerts=payload.no_alerts,
                sample=payload.sample,
                verbose=True,
            )
            run_registry.mark_completed(run_id)
            logger.info("Background execution completed.")
        except Exception as e:
            run_registry.mark_failed(run_id, str(e))
            logger.error("Pipeline crashed during API execution: {}", e)

    background_tasks.add_task(run_pipeline_task)
    return {
        "status": "queued",
        "run_id": run_id,
        "message": "Pipeline triggered asynchronously. Poll /pipeline/status/{run_id}.",
        "params": payload.model_dump(),
    }
```

New endpoint:

```python
@app.get("/pipeline/status/{run_id}")
def get_pipeline_status(
    run_id: str,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Return the status of a background pipeline run."""
    rec = run_registry.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return rec
```

- [ ] **Step 4: Run tests** — `.venv/bin/python -m pytest tests/test_api.py -v` → PASS.

- [ ] **Step 5: Frontend polish (small):** in `frontend/src/lib/api.ts` add `run_id: string` to the trigger response type and a `getPipelineStatus(runId: string)` method hitting `/api/proxy/pipeline/status/${runId}`; on the dashboard (`frontend/src/app/page.tsx`), after triggering, poll every 3s until `completed`/`failed` and show a status badge instead of the static "queued" message. Follow existing fetch patterns in `api.ts`. Add a matching test in `frontend/src/lib/api.test.ts` mirroring an existing api-method test.

- [ ] **Step 6: Run frontend tests** — `cd frontend && npm test` → PASS.

- [ ] **Step 7: Commit**

```bash
git add src/api/run_registry.py src/api/app.py tests/test_api.py frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/app/page.tsx
git commit -m "feat: pipeline run registry with status endpoint and dashboard polling"
```

---

### Task 4: Real Slack adapter for actions

`SlackWebhookAdapter` posts a formatted message to `SLACK_WEBHOOK_URL` via httpx. Factory picks it when the env var is set, else keeps the mock — so local dev is unchanged.

**Files:**
- Modify: `src/actions/adapters.py` (add `SlackWebhookAdapter`, `build_default_adapter()`)
- Modify: `src/actions/service.py:17` (`self.adapter = adapter or build_default_adapter()`)
- Test: `tests/test_action_service.py`

**Interfaces:**
- Produces: `build_default_adapter() -> BaseActionAdapter`; `SlackWebhookAdapter(webhook_url: str)` implementing `execute(action_type, payload) -> Tuple[bool, str, Dict]`.

- [ ] **Step 1: Write failing tests** (`tests/test_action_service.py`):

```python
import pytest
import respx  # if respx isn't installed, monkeypatch httpx.AsyncClient.post instead
import httpx
from src.actions.adapters import SlackWebhookAdapter, build_default_adapter, GenericWebhookAdapter

class TestSlackAdapter:
    @pytest.mark.asyncio
    async def test_posts_payload_and_succeeds(self, monkeypatch):
        async def fake_post(self, url, json=None, **kwargs):
            assert "hooks.slack" in url
            assert "VENDOR_FOLLOW_UP" in json["text"]
            return httpx.Response(200, text="ok")
        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        adapter = SlackWebhookAdapter("https://hooks.slack.example/T000/B000/XXX")
        ok, reason, resp = await adapter.execute("VENDOR_FOLLOW_UP", {"note": "check PO 123"})
        assert ok is True and reason == ""

    @pytest.mark.asyncio
    async def test_http_error_reports_failure(self, monkeypatch):
        async def fake_post(self, url, json=None, **kwargs):
            return httpx.Response(500, text="internal error")
        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        adapter = SlackWebhookAdapter("https://hooks.slack.example/T000/B000/XXX")
        ok, reason, resp = await adapter.execute("STORE_CHECK", {})
        assert ok is False and "500" in reason

def test_factory_uses_slack_when_env_set(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/x")
    assert isinstance(build_default_adapter(), SlackWebhookAdapter)

def test_factory_falls_back_to_mock(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert isinstance(build_default_adapter(), GenericWebhookAdapter)
```

(Check how existing async tests in this file are marked — reuse that pattern; drop `respx` import, it isn't used.)

- [ ] **Step 2: Run to verify failure** — ImportError on `SlackWebhookAdapter`.

- [ ] **Step 3: Implement in `src/actions/adapters.py`**

```python
import os
import httpx


class SlackWebhookAdapter(BaseActionAdapter):
    """Posts action requests to a Slack incoming webhook."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def execute(self, action_type: str, payload: dict) -> Tuple[bool, str, Dict[str, Any]]:
        note = payload.get("note") or payload.get("comment") or ""
        exception_id = payload.get("exception_id", "unknown")
        text = (
            f":package: *Triage Action: {action_type}*\n"
            f"Exception: `{exception_id}`\n"
            f"{note}".strip()
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json={"text": text})
            if response.status_code >= 400:
                return False, f"Slack webhook returned HTTP {response.status_code}", {
                    "status_code": response.status_code, "body": response.text[:500],
                }
            return True, "", {"status": "delivered", "status_code": response.status_code}
        except httpx.HTTPError as e:
            return False, f"Slack webhook request failed: {e}", {}


def build_default_adapter() -> BaseActionAdapter:
    """Slack adapter when SLACK_WEBHOOK_URL is configured, otherwise the mock."""
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if url:
        return SlackWebhookAdapter(url)
    return GenericWebhookAdapter()
```

In `src/actions/service.py`, change the import and constructor line:

```python
from src.actions.adapters import BaseActionAdapter, GenericWebhookAdapter, build_default_adapter
...
        self.adapter = adapter or build_default_adapter()
```

- [ ] **Step 4: Run tests** — `.venv/bin/python -m pytest tests/test_action_service.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/adapters.py src/actions/service.py tests/test_action_service.py
git commit -m "feat: Slack webhook adapter for downstream actions with env-based factory"
```

---

### Task 5: Override analytics endpoint + planner-review stats strip

**Files:**
- Modify: `src/db/store.py` (add `get_override_stats()`)
- Modify: `src/api/app.py` (add `GET /overrides/stats` — **must be registered before** `POST /overrides/{override_id}/...` routes are not affected, but keep it above any future `GET /overrides/{id}` route)
- Modify: `frontend/src/lib/api.ts`, `frontend/src/app/planner-review/page.tsx`
- Test: `tests/test_db_store.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `OverrideStore.get_override_stats() -> dict` shaped `{"total": int, "by_status": {status: count}, "by_override_priority": {priority: count}}`.

- [ ] **Step 1: Write failing test** (`tests/test_db_store.py`, using its existing tmp-db fixture pattern):

```python
def test_get_override_stats(tmp_store):
    tmp_store.insert_override(
        exception_id="EXC-1", run_date="2026-07-01", analyst_username="a",
        enriched_input_snapshot={}, override_priority="CRITICAL",
    )
    tmp_store.insert_override(
        exception_id="EXC-2", run_date="2026-07-01", analyst_username="a",
        enriched_input_snapshot={}, override_priority="LOW",
    )
    tmp_store.approve_override(1, approved_by="p")
    stats = tmp_store.get_override_stats()
    assert stats["total"] == 2
    assert stats["by_status"]["approved"] == 1
    assert stats["by_status"]["pending"] == 1
    assert stats["by_override_priority"]["CRITICAL"] == 1
```

(Match the real column/status names by reading `src/db/store.py` schema first; adjust `"approved"`/`"pending"` literals to the store's actual status values.)

- [ ] **Step 2: Run to verify failure** — AttributeError `get_override_stats`.

- [ ] **Step 3: Implement in `src/db/store.py`** (match the file's existing connection helper style):

```python
    def get_override_stats(self) -> dict:
        """Aggregate override counts for the analytics strip."""
        with self._connect() as conn:  # use the file's actual connection pattern
            total = conn.execute("SELECT COUNT(*) FROM overrides").fetchone()[0]
            by_status = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT status, COUNT(*) FROM overrides GROUP BY status"
                )
            }
            by_priority = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT override_priority, COUNT(*) FROM overrides "
                    "WHERE override_priority IS NOT NULL GROUP BY override_priority"
                )
            }
        return {"total": total, "by_status": by_status, "by_override_priority": by_priority}
```

- [ ] **Step 4: Add endpoint in `src/api/app.py`** (place directly after `list_pending_overrides`):

```python
@app.get("/overrides/stats")
def get_override_stats(
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Aggregate override statistics for the active-learning dashboard."""
    try:
        return override_store.get_override_stats()
    except Exception as e:
        logger.error("Failed to compute override stats: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

Add an API test in `tests/test_api.py`:

```python
def test_override_stats_endpoint(auth):
    resp = client.get("/overrides/stats", auth=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"total", "by_status", "by_override_priority"}
```

- [ ] **Step 5: Run backend tests** — `.venv/bin/python -m pytest tests/test_db_store.py tests/test_api.py -v` → PASS.

- [ ] **Step 6: Frontend strip.** In `frontend/src/lib/api.ts` add:

```typescript
export interface OverrideStats {
  total: number;
  by_status: Record<string, number>;
  by_override_priority: Record<string, number>;
}
```

and an `api.getOverrideStats(): Promise<OverrideStats>` method (`GET /api/proxy/overrides/stats`, mirroring existing methods). In `frontend/src/app/planner-review/page.tsx`, fetch stats on mount alongside pending overrides and render a row of small cards above the pending list: Total, Pending, Approved, Rejected, and a per-priority count line — reuse the page's existing card/Tailwind classes. Add one test in `frontend/src/lib/api.test.ts` for the new method.

- [ ] **Step 7: Run frontend tests** — `cd frontend && npm test` → PASS.

- [ ] **Step 8: Commit**

```bash
git add src/db/store.py src/api/app.py tests/test_db_store.py tests/test_api.py frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/app/planner-review/page.tsx
git commit -m "feat: override analytics endpoint and planner-review stats strip"
```

---

### Task 6: Action History page

Backend (`GET /actions` with pagination/filters) already exists, as do `ActionRecord`/`PaginatedActions` types in `api.ts`. This task is frontend-only. Design reference: `docs/` action-history design doc (commit fd0b117) — follow it where it exists, this plan where it's silent.

**Files:**
- Create: `frontend/src/app/actions/page.tsx`
- Modify: `frontend/src/lib/api.ts` (only if `getAllActions` isn't already there — check first)
- Test: `frontend/src/app/actions/page.test.tsx` (or colocated per repo convention — match how `ExceptionCard.test.tsx` sits next to its component)

**Interfaces:**
- Consumes: `api.getAllActions({limit, offset, status?, action_type?, run_date?}) -> PaginatedActions`; types `ActionRecord`, `ActionStatus`, `AnyActionType` from `frontend/src/lib/api.ts`.

- [ ] **Step 1: Verify/add the api method.** Check `frontend/src/lib/api.ts` for a method calling `GET /api/proxy/actions` with query params. If missing, add `getAllActions(params)` building a `URLSearchParams` from defined params only, mirroring existing method style, plus a test in `api.test.ts`.

- [ ] **Step 2: Write failing page tests** (mock `api` module the same way `ExceptionCard.test.tsx` does):

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import ActionsPage from "./page";
import { api } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  ...jest.requireActual("../../lib/api"),
  api: { getAllActions: jest.fn() },
}));

const record = {
  request_id: "req-1", exception_id: "EXC-1", run_date: "2026-07-01",
  action_type: "VENDOR_FOLLOW_UP", status: "completed",
  requested_by: "alice", requested_by_role: "planner",
  payload: {}, created_at: "2026-07-01T09:00:00Z", updated_at: "2026-07-01T09:00:05Z",
};

test("renders action rows", async () => {
  (api.getAllActions as jest.Mock).mockResolvedValue({ items: [record], total: 1, limit: 50, offset: 0 });
  render(<ActionsPage />);
  await waitFor(() => expect(screen.getByText("EXC-1")).toBeInTheDocument());
  expect(screen.getByText("VENDOR_FOLLOW_UP")).toBeInTheDocument();
});

test("shows empty state", async () => {
  (api.getAllActions as jest.Mock).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
  render(<ActionsPage />);
  await waitFor(() => expect(screen.getByText(/no actions/i)).toBeInTheDocument());
});
```

(Adjust `record` fields and the `PaginatedActions` shape to the real interfaces in `api.ts` — read them before writing.)

- [ ] **Step 3: Run to verify failure** — `cd frontend && npm test -- actions` → FAIL (page missing).

- [ ] **Step 4: Implement `frontend/src/app/actions/page.tsx`** as a `"use client"` page modeled on `settings/page.tsx`'s structure: header + back-link, filter row (three `<select>`s: status, action type, run date — run dates from `api.getRuns()` if that method exists, else a text input), a table of actions (columns: created_at, exception_id, action_type, status badge, requested_by, failure_reason when failed), Prev/Next pagination buttons driven by `offset`/`total`, an empty state ("No actions recorded yet."), and the standard backend-unavailable error banner (`BACKEND_UNAVAILABLE_MESSAGE`). Reuse the `Badge` styling pattern from the settings page for status colors (completed→ok, failed→error, sent/queued→warn). Refetch whenever a filter or page changes.

- [ ] **Step 5: Add nav link.** Add a link to `/actions` wherever `/settings` and `/planner-review` links live (check `frontend/src/app/page.tsx` / `layout.tsx`).

- [ ] **Step 6: Run frontend tests** — `cd frontend && npm test` → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/actions/ frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/app/page.tsx
git commit -m "feat: action history page with filters and pagination"
```

---

### Task 7: Scheduled daily run + briefing dispatch script

Prototype-weight scheduling: a single script that runs the pipeline and posts the briefing to Slack/email using the existing `AlertDispatcher` machinery, plus a documented cron line. No daemon, no queue.

**Files:**
- Create: `scripts/run_daily.py`
- Modify: `README.md` (short "Scheduling" section)
- Test: `tests/test_run_daily.py`

**Interfaces:**
- Consumes: `run_triage_pipeline` from `src.main`; briefing file at `output/briefings/briefing_<date>.md`; `httpx.post(url, json={"text": ...})` webhook convention from `AlertDispatcher._send_webhook`.
- Produces: `dispatch_briefing(run_date: str, webhook_url: str) -> bool` (importable for tests), CLI entry `python scripts/run_daily.py [--date YYYY-MM-DD] [--dry-run]`.

- [ ] **Step 1: Write failing tests** (`tests/test_run_daily.py`):

```python
from __future__ import annotations

import httpx
import pytest

from scripts.run_daily import dispatch_briefing


def test_dispatch_briefing_posts_content(tmp_path, monkeypatch):
    briefing_dir = tmp_path / "output" / "briefings"
    briefing_dir.mkdir(parents=True)
    (briefing_dir / "briefing_2026-07-04.md").write_text("# Morning Briefing\nAll clear.")
    monkeypatch.chdir(tmp_path)

    calls = {}
    def fake_post(url, json=None, timeout=None):
        calls["url"], calls["json"] = url, json
        return httpx.Response(200, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)

    assert dispatch_briefing("2026-07-04", "https://hooks.slack.example/x") is True
    assert "Morning Briefing" in calls["json"]["text"]


def test_dispatch_briefing_missing_file_returns_false(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert dispatch_briefing("2026-07-04", "https://hooks.slack.example/x") is False
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_run_daily.py -v` → import error. (If `scripts/` isn't importable, add an empty `scripts/__init__.py` or match how `tests/test_backtest.py` imports from `scripts/`.)

- [ ] **Step 3: Implement `scripts/run_daily.py`**

```python
"""Run the daily triage pipeline and post the briefing to Slack.

Usage:
    .venv/bin/python scripts/run_daily.py [--date YYYY-MM-DD] [--dry-run]

Designed for cron. Exits non-zero if the pipeline fails.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def dispatch_briefing(run_date: str, webhook_url: str) -> bool:
    """Post the day's briefing markdown to a Slack-style webhook."""
    briefing_path = Path("output/briefings") / f"briefing_{run_date}.md"
    if not briefing_path.exists():
        logger.warning("No briefing found at {} — skipping dispatch", briefing_path)
        return False
    content = briefing_path.read_text(encoding="utf-8")
    try:
        response = httpx.post(webhook_url, json={"text": content}, timeout=10.0)
        response.raise_for_status()
        logger.info("Briefing for {} dispatched to webhook", run_date)
        return True
    except httpx.HTTPError as e:
        logger.error("Failed to dispatch briefing: {}", e)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily triage run + briefing dispatch")
    parser.add_argument("--date", default=str(date.today()), help="Run date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    args = parser.parse_args()

    from src.main import run_triage_pipeline

    try:
        run_triage_pipeline(
            config_path="config/config.yaml",
            run_date=args.date,
            dry_run=args.dry_run,
            no_alerts=False,
            sample=True,
            verbose=False,
        )
    except Exception as e:
        logger.error("Daily pipeline run failed: {}", e)
        return 1

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if webhook_url:
        dispatch_briefing(args.date, webhook_url)
    else:
        logger.info("SLACK_WEBHOOK_URL not set — briefing not dispatched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

(Check `run_triage_pipeline`'s actual signature in `src/main.py` before finalizing the kwargs — they must match what `app.py` passes.)

- [ ] **Step 4: Run tests** — `.venv/bin/python -m pytest tests/test_run_daily.py -v` → PASS.

- [ ] **Step 5: Document in README** — add a "Scheduling" section:

```markdown
## Scheduling a Daily Run

Run the pipeline every weekday at 6:00 AM and post the briefing to Slack:

​```cron
0 6 * * 1-5 cd /path/to/AI-driven-replenishment-exception-triage-agent && .venv/bin/python scripts/run_daily.py >> output/cron.log 2>&1
​```

Set `SLACK_WEBHOOK_URL` in `.env` to enable briefing dispatch; without it the pipeline still runs and writes `output/briefings/`.
```

- [ ] **Step 6: Run full backend suite** — `.venv/bin/python -m pytest tests/ -v` → all PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_daily.py tests/test_run_daily.py README.md
git commit -m "feat: daily run script with Slack briefing dispatch and cron docs"
```

---

## Deliberately Out of Scope (prototype)

- Password hashing / sessions / JWT — plaintext `API_USERS` is documented as prototype-only.
- Persisting run status across restarts — in-memory registry is enough for a single-process prototype.
- Migrating queue JSON files into SQLite — larger refactor; revisit only if cross-run search becomes a real need.
- SSE/WebSocket live updates — polling covers it.
- ERP-specific adapters beyond Slack.
