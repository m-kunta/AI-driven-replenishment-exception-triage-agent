# Settings Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a planner-gated edit mode to the Settings page that writes changed values to `.env` atomically, validates all fields server-side, and logs every change to `actions.db`.

**Architecture:** A new `EnvWriter` utility class owns all `.env` read/write/validate logic. Two new endpoints (`PATCH /settings`, `POST /settings/validate-model`) sit in `app.py` and delegate to `EnvWriter`. The Settings page gains a React edit-mode toggle (Option B — whole-page mode switch with Apply/Discard) backed by session-only draft state. Analysts see the page read-only; planners get the edit controls.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic v2, loguru, pytest; Next.js 16, React, TypeScript, `fetch` via existing BFF proxy.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/api/env_writer.py` | Create | Allowlist, per-field validation, atomic `.env` write |
| `src/api/app.py` | Modify | Add `PATCH /settings`, `POST /settings/validate-model` |
| `src/models.py` | Modify | Add `SETTINGS_CHANGE` to `ActionType` enum |
| `src/db/action_store.py` | Modify | Add optional `status` param to `insert_action()` |
| `src/utils/config_loader.py` | Modify | Add `OLLAMA_BASE_URL` env override |
| `frontend/src/lib/api.ts` | Modify | Add `SETTINGS_CHANGE` to `ActionType`; new types + methods |
| `frontend/src/app/settings/page.tsx` | Modify | Edit mode toggle, draft state, editable inputs, apply flow |
| `tests/test_api.py` | Modify | Tests for both new endpoints |

---

## Task 1: Add `SETTINGS_CHANGE` to `ActionType` and `status` param to `insert_action()`

**Files:**
- Modify: `src/models.py`
- Modify: `src/db/action_store.py`
- Test: `tests/test_api.py` (existing test suite must stay green)

- [ ] **Step 1: Add `SETTINGS_CHANGE` to `ActionType` enum in `src/models.py`**

Open `src/models.py` and add the new member to `ActionType`:

```python
class ActionType(str, enum.Enum):
    CREATE_REVIEW = "CREATE_REVIEW"
    REQUEST_VERIFICATION = "REQUEST_VERIFICATION"
    VENDOR_FOLLOW_UP = "VENDOR_FOLLOW_UP"
    STORE_CHECK = "STORE_CHECK"
    DEFER = "DEFER"
    SETTINGS_CHANGE = "SETTINGS_CHANGE"
```

- [ ] **Step 2: Add optional `status` parameter to `insert_action()` in `src/db/action_store.py`**

Replace the `insert_action` signature and the hardcoded `'queued'` literal:

```python
def insert_action(
    self,
    request_id: str,
    exception_id: str,
    run_date: str,
    action_type: str,
    requested_by: str,
    requested_by_role: str,
    payload: dict,
    status: str = "queued",
) -> dict:
    """Insert a new action. If request_id exists, return the existing record (idempotency)."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        self._conn.execute(
            """
            INSERT INTO action_records (
                request_id, exception_id, run_date, action_type,
                requested_by, requested_by_role, payload, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id, exception_id, run_date, action_type,
                requested_by, requested_by_role, json.dumps(payload),
                status, now, now
            )
        )
        self._conn.commit()
    except sqlite3.IntegrityError:
        pass

    res = self.get_action(request_id)
    if not res:
        raise RuntimeError("Failed to retrieve action record after insert.")
    return res
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
.venv/bin/python -m pytest tests/ -v -x
```

Expected: all existing tests pass (the default `status="queued"` preserves backward compatibility).

- [ ] **Step 4: Commit**

```bash
git add src/models.py src/db/action_store.py
git commit -m "feat: add SETTINGS_CHANGE action type and status param to insert_action"
```

---

## Task 2: Add `OLLAMA_BASE_URL` env override to `config_loader.py`

**Files:**
- Modify: `src/utils/config_loader.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to the `TestSettingsEndpoint` class in `tests/test_api.py`:

```python
def test_settings_returns_ollama_base_url_env_override(self, client, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-ollama:11434")

    with patch("src.api.app.load_config") as mock_load_config:
        cfg = mock_load_config.return_value
        cfg.agent.provider = "ollama"
        cfg.agent.model = "llama3.2"
        cfg.agent.batch_size = 10
        cfg.agent.max_tokens = 8000
        cfg.agent.retry_attempts = 3
        cfg.agent.ollama_base_url = "http://custom-ollama:11434"

        resp = client.get("/settings", auth=VALID_CREDS)

    assert resp.status_code == 200
    assert resp.json()["agent"]["ollama_base_url"] == "http://custom-ollama:11434"
```

- [ ] **Step 2: Run test to confirm it fails for the right reason**

```bash
.venv/bin/python -m pytest tests/test_api.py -k "test_settings_returns_ollama_base_url_env_override" -v
```

Expected: FAIL — the mock makes this pass trivially; the real test of the override is in config_loader. Add a config_loader-level test instead in a new file `tests/test_config_loader.py`:

```python
"""Tests for OLLAMA_BASE_URL env override in config_loader."""
from __future__ import annotations

import pytest
import yaml

from src.utils.config_loader import load_config

_MINIMAL_YAML = yaml.dump({
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "batch_size": 10,
        "max_tokens": 8000,
        "retry_attempts": 3,
        "ollama_base_url": "http://localhost:11434",
    },
    "ingestion": {"adapter": "csv"},
    "output": {"log_dir": "output/logs"},
})


def test_ollama_base_url_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-ollama:9999")
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_YAML)

    # load_config takes a config_path argument — pass the tmp file directly
    cfg = load_config(config_path=str(cfg_path))

    assert cfg.agent.ollama_base_url == "http://custom-ollama:9999"


def test_ollama_base_url_env_override_absent_uses_yaml(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_YAML)

    cfg = load_config(config_path=str(cfg_path))

    assert cfg.agent.ollama_base_url == "http://localhost:11434"
```

- [ ] **Step 3: Run the new tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_config_loader.py -v
```

Expected: FAIL — `_CONFIG_PATH` constant doesn't exist yet as a patchable symbol (or the override logic is missing). Check the exact failure message.

- [ ] **Step 4: Add the `OLLAMA_BASE_URL` env override in `_apply_agent_env_overrides()` in `src/utils/config_loader.py`**

Locate `_apply_agent_env_overrides` and add after the existing `model_override` block:

```python
def _apply_agent_env_overrides(resolved_config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply optional env-driven agent overrides without requiring YAML edits."""
    agent_cfg = resolved_config.setdefault("agent", {})

    provider_override = os.environ.get("AGENT_PROVIDER", "").strip().lower()
    model_override = os.environ.get("AGENT_MODEL", "").strip()
    ollama_base_url_override = os.environ.get("OLLAMA_BASE_URL", "").strip()  # NEW

    if provider_override:
        if provider_override not in _SUPPORTED_PROVIDERS:
            raise ConfigurationError(
                f"Invalid AGENT_PROVIDER: {provider_override!r}. "
                f"Must be one of: {', '.join(_SUPPORTED_PROVIDERS)}"
            )
        previous_provider = str(agent_cfg.get("provider", "")).strip().lower()
        previous_model = str(agent_cfg.get("model", "")).strip()
        agent_cfg["provider"] = provider_override

        if model_override:
            agent_cfg["model"] = model_override
        elif previous_provider != provider_override or not previous_model:
            agent_cfg["model"] = _DEFAULT_MODELS[provider_override]
    elif model_override:
        agent_cfg["model"] = model_override

    if ollama_base_url_override:                          # NEW
        agent_cfg["ollama_base_url"] = ollama_base_url_override  # NEW

    return resolved_config
```

- [ ] **Step 5: Run the config_loader tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_config_loader.py -v
```

Expected: PASS for both tests.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
.venv/bin/python -m pytest tests/ -v -x
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/utils/config_loader.py tests/test_config_loader.py
git commit -m "feat: add OLLAMA_BASE_URL env override to config_loader"
```

---

## Task 3: Create `EnvWriter` — `.env` validation and atomic write

**Files:**
- Create: `src/api/env_writer.py`
- Test: `tests/test_env_writer.py`

- [ ] **Step 1: Write failing tests in `tests/test_env_writer.py`**

```python
"""Tests for EnvWriter — .env validation and atomic write."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.api.env_writer import EnvWriter, EnvValidationError

ALLOWLIST = {"AGENT_PROVIDER", "AGENT_MODEL", "API_USER_ROLE", "API_USER_ROLES",
             "OLLAMA_BASE_URL", "BACKEND_PORT"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_provider_passes(self):
        errors = EnvWriter.validate({"AGENT_PROVIDER": "openai"})
        assert errors == {}

    def test_invalid_provider_fails(self):
        errors = EnvWriter.validate({"AGENT_PROVIDER": "unknown_llm"})
        assert "AGENT_PROVIDER" in errors

    def test_valid_role_passes(self):
        errors = EnvWriter.validate({"API_USER_ROLE": "planner"})
        assert errors == {}

    def test_invalid_role_fails(self):
        errors = EnvWriter.validate({"API_USER_ROLE": "admin"})
        assert "API_USER_ROLE" in errors

    def test_valid_user_roles_passes(self):
        errors = EnvWriter.validate({"API_USER_ROLES": "alice:planner,bob:analyst"})
        assert errors == {}

    def test_invalid_user_roles_bad_format_fails(self):
        errors = EnvWriter.validate({"API_USER_ROLES": "alice-planner"})
        assert "API_USER_ROLES" in errors

    def test_invalid_user_roles_bad_role_fails(self):
        errors = EnvWriter.validate({"API_USER_ROLES": "alice:superadmin"})
        assert "API_USER_ROLES" in errors

    def test_valid_port_passes(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "8080"})
        assert errors == {}

    def test_port_below_range_fails(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "80"})
        assert "BACKEND_PORT" in errors

    def test_port_above_range_fails(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "99999"})
        assert "BACKEND_PORT" in errors

    def test_non_numeric_port_fails(self):
        errors = EnvWriter.validate({"BACKEND_PORT": "abc"})
        assert "BACKEND_PORT" in errors

    def test_valid_ollama_url_passes(self):
        errors = EnvWriter.validate({"OLLAMA_BASE_URL": "http://localhost:11434"})
        assert errors == {}

    def test_invalid_ollama_url_fails(self):
        errors = EnvWriter.validate({"OLLAMA_BASE_URL": "ftp://bad"})
        assert "OLLAMA_BASE_URL" in errors

    def test_key_outside_allowlist_fails(self):
        errors = EnvWriter.validate({"API_PASSWORD": "secret"})
        assert "API_PASSWORD" in errors

    def test_empty_model_fails(self):
        errors = EnvWriter.validate({"AGENT_MODEL": ""})
        assert "AGENT_MODEL" in errors

    def test_non_empty_model_passes(self):
        errors = EnvWriter.validate({"AGENT_MODEL": "gpt-4.1"})
        assert errors == {}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

class TestWrite:
    def test_updates_existing_key(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("AGENT_PROVIDER=claude\nAPI_PASSWORD=secret\n")

        EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)

        content = env.read_text()
        assert "AGENT_PROVIDER=openai" in content
        assert "API_PASSWORD=secret" in content  # untouched

    def test_appends_missing_key(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("API_PASSWORD=secret\n")

        EnvWriter.apply({"AGENT_MODEL": "gpt-4.1"}, env_path=env)

        assert "AGENT_MODEL=gpt-4.1" in env.read_text()

    def test_preserves_comments(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# provider\nAGENT_PROVIDER=claude\n")

        EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)

        assert "# provider" in env.read_text()

    def test_write_is_atomic(self, tmp_path):
        """Verify no partial write: original is intact if an error occurs mid-write."""
        env = tmp_path / ".env"
        original = "AGENT_PROVIDER=claude\n"
        env.write_text(original)

        # Simulate error mid-write by passing a non-writable dir
        bad_path = tmp_path / "no_such_dir" / ".env"
        with pytest.raises(Exception):
            EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=bad_path)

        # Original is intact
        assert env.read_text() == original

    def test_returns_applied_and_restart_required(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("AGENT_PROVIDER=claude\n")

        result = EnvWriter.apply({"AGENT_PROVIDER": "openai"}, env_path=env)

        assert "AGENT_PROVIDER" in result["applied"]
        assert "AGENT_PROVIDER" in result["restart_required"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_env_writer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.api.env_writer'`

- [ ] **Step 3: Create `src/api/env_writer.py`**

```python
"""Utility for safe, atomic .env mutation from the Settings API."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_ENV_PATH = _REPO_ROOT / ".env"

_ALLOWLIST: set[str] = {
    "AGENT_PROVIDER",
    "AGENT_MODEL",
    "API_USER_ROLE",
    "API_USER_ROLES",
    "OLLAMA_BASE_URL",
    "BACKEND_PORT",
}

_ALL_RESTART_REQUIRED: set[str] = _ALLOWLIST  # every editable key requires restart

_VALID_PROVIDERS = {"claude", "openai", "gemini", "ollama"}
_VALID_ROLES = {"analyst", "planner"}


class EnvValidationError(ValueError):
    pass


class EnvWriter:
    """Validates and atomically writes a subset of .env keys."""

    @staticmethod
    def validate(payload: Dict[str, str]) -> Dict[str, str]:
        """Validate a partial settings payload.

        Returns a dict of {key: error_message} for every invalid or
        disallowed key. An empty dict means the payload is valid.
        """
        errors: Dict[str, str] = {}

        for key, value in payload.items():
            if key not in _ALLOWLIST:
                errors[key] = f"Key '{key}' is not editable via the API."
                continue

            if key == "AGENT_PROVIDER":
                if value not in _VALID_PROVIDERS:
                    errors[key] = (
                        f"Must be one of: {', '.join(sorted(_VALID_PROVIDERS))}."
                    )

            elif key == "AGENT_MODEL":
                if not value.strip():
                    errors[key] = "Model name must not be empty."

            elif key == "API_USER_ROLE":
                if value not in _VALID_ROLES:
                    errors[key] = "Must be 'analyst' or 'planner'."

            elif key == "API_USER_ROLES":
                err = EnvWriter._validate_user_roles(value)
                if err:
                    errors[key] = err

            elif key == "OLLAMA_BASE_URL":
                if not (value.startswith("http://") or value.startswith("https://")):
                    errors[key] = "Must be a valid URL starting with http:// or https://."

            elif key == "BACKEND_PORT":
                try:
                    port = int(value)
                    if not (1024 <= port <= 65535):
                        raise ValueError
                except ValueError:
                    errors[key] = "Must be an integer between 1024 and 65535."

        return errors

    @staticmethod
    def _validate_user_roles(value: str) -> str:
        """Return an error string or empty string for API_USER_ROLES value."""
        if not value.strip():
            return ""  # empty is valid (clears all role mappings)
        for entry in value.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                return f"Entry '{entry}' must use username:role format."
            username, role = (p.strip() for p in entry.split(":", 1))
            if not username:
                return "Each entry must include a username."
            if role not in _VALID_ROLES:
                return f"Role '{role}' must be 'analyst' or 'planner'."
        return ""

    @staticmethod
    def apply(
        payload: Dict[str, str],
        env_path: Path = _DEFAULT_ENV_PATH,
    ) -> Dict[str, Any]:
        """Atomically write the payload keys to the .env file.

        Updates existing KEY=value lines in-place, appends missing keys.
        Preserves comments and ordering. Uses a temp file + os.replace()
        for atomicity.

        Returns:
            {"applied": [...], "restart_required": [...], "errors": {}}
        """
        # Read existing file, or start empty
        if env_path.exists():
            lines = env_path.read_text().splitlines(keepends=True)
        else:
            lines = []

        updated_keys: set[str] = set()
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in payload:
                new_lines.append(f"{key}={payload[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)

        # Append keys that weren't already in the file
        for key, value in payload.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}\n")

        # Atomic write via temp file in the same directory
        env_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=env_path.parent, prefix=".env.tmp.")
        try:
            with os.fdopen(fd, "w") as f:
                f.writelines(new_lines)
            os.replace(tmp, env_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        applied = list(payload.keys())
        restart_required = [k for k in applied if k in _ALL_RESTART_REQUIRED]
        return {"applied": applied, "restart_required": restart_required, "errors": {}}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_env_writer.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v -x
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/api/env_writer.py tests/test_env_writer.py
git commit -m "feat: add EnvWriter for atomic .env validation and write"
```

---

## Task 4: Add `PATCH /settings` and `POST /settings/validate-model` endpoints

**Files:**
- Modify: `src/api/app.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add a new test class to `tests/test_api.py`. Add these imports at the top of the file if not already present:

```python
import uuid
from datetime import date
```

Then add the class after the existing `TestSettingsEndpoint` class:

```python
# ===========================================================================
# PATCH /settings
# ===========================================================================

class TestPatchSettingsEndpoint:
    def _planner_client(self, monkeypatch):
        """Return a TestClient where the authed user resolves to planner role."""
        monkeypatch.setenv("API_USER_ROLES", f"{_USERNAME}:planner")
        return TestClient(app)

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
        env_file = tmp_path / ".env"
        env_file.write_text("AGENT_PROVIDER=claude\n")
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
```

Also add `MagicMock` to the imports at the top:

```python
from unittest.mock import MagicMock, patch
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_api.py -k "TestPatchSettings or TestValidateModel" -v
```

Expected: FAIL with `404 Not Found` (endpoints don't exist yet).

- [ ] **Step 3: Add Pydantic request models and two endpoints to `src/api/app.py`**

Add after the existing imports at the top of `app.py`:

```python
from src.api.env_writer import EnvWriter
```

Add these Pydantic request models near the other models in `app.py` (e.g. after `PipelineTriggerRequest`):

```python
class PatchSettingsRequest(BaseModel):
    """Partial .env update payload — only allowlisted keys accepted."""
    __root__: Dict[str, str]


class ValidateModelRequest(BaseModel):
    provider: str
    model: str
    ollama_base_url: Optional[str] = None
```

Add these two endpoints after the existing `GET /settings` endpoint:

```python
@app.patch("/settings")
def patch_settings(
    payload: Dict[str, str],
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Write a partial .env update. Planner-only. Validates all fields before writing."""
    role = get_current_user_role(username)
    if role != "planner":
        raise HTTPException(status_code=403, detail="Planner role required to edit settings.")

    errors = EnvWriter.validate(payload)
    if errors:
        raise HTTPException(status_code=422, detail=None, headers=None)

    from fastapi.responses import JSONResponse as _JSONResponse
    if errors:
        return _JSONResponse(status_code=422, content={"errors": errors})

    result = EnvWriter.apply(payload)

    run_date_str = str(date.today())
    for key in result["applied"]:
        try:
            action_store.insert_action(
                request_id=str(uuid.uuid4()),
                exception_id="__settings__",
                run_date=run_date_str,
                action_type="SETTINGS_CHANGE",
                requested_by=username,
                requested_by_role=role,
                payload={"key": key, "restart_required": key in result["restart_required"]},
                status="completed",
            )
        except Exception as e:
            logger.error("Failed to write settings audit record for key {}: {}", key, e)

    return result


@app.post("/settings/validate-model")
def validate_model(
    body: ValidateModelRequest,
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Validate a draft provider/model combination against the provider's live model list."""
    role = get_current_user_role(username)
    if role != "planner":
        raise HTTPException(status_code=403, detail="Planner role required.")

    if body.provider not in {"claude", "openai", "gemini", "ollama"}:
        raise HTTPException(status_code=422, detail=f"Unsupported provider: {body.provider!r}")

    try:
        cfg = load_config()
        from src.utils.config_loader import AgentConfig
        draft_agent_cfg = AgentConfig(
            provider=body.provider,
            model=body.model,
            anthropic_api_key=cfg.agent.anthropic_api_key,
            openai_api_key=cfg.agent.openai_api_key,
            gemini_api_key=cfg.agent.gemini_api_key,
            ollama_base_url=body.ollama_base_url or cfg.agent.ollama_base_url,
        )
        provider = get_provider(draft_agent_cfg)
        models = provider.list_models()
        return {
            "provider": body.provider,
            "model": body.model,
            "models": models,
            "model_available": body.model in models,
        }
    except Exception as e:
        logger.warning("validate_model failed for provider={} model={}: {}", body.provider, body.model, e)
        raise HTTPException(status_code=422, detail={"error": str(e), "models": []})
```

Also add these imports near the top of `app.py` (with the other stdlib imports):

```python
import uuid
from datetime import date
```

- [ ] **Step 4: Fix the `patch_settings` endpoint — the double-check pattern is messy**

The endpoint above has a logic error (checks `errors` twice). Replace the endpoint body with the clean version:

```python
@app.patch("/settings")
def patch_settings(
    payload: Dict[str, str],
    username: Annotated[str, Depends(get_current_username)],
) -> Dict[str, Any]:
    """Write a partial .env update. Planner-only. Validates all fields before writing."""
    role = get_current_user_role(username)
    if role != "planner":
        raise HTTPException(status_code=403, detail="Planner role required to edit settings.")

    errors = EnvWriter.validate(payload)
    if errors:
        from fastapi.responses import JSONResponse as _JSONResponse
        return _JSONResponse(status_code=422, content={"errors": errors})

    result = EnvWriter.apply(payload)

    run_date_str = str(date.today())
    for key in result["applied"]:
        try:
            action_store.insert_action(
                request_id=str(uuid.uuid4()),
                exception_id="__settings__",
                run_date=run_date_str,
                action_type="SETTINGS_CHANGE",
                requested_by=username,
                requested_by_role=role,
                payload={"key": key, "restart_required": key in result["restart_required"]},
                status="completed",
            )
        except Exception as e:
            logger.error("Failed to write settings audit record for key {}: {}", key, e)

    return result
```

- [ ] **Step 5: Check `AgentConfig` import path**

```bash
grep -n "class AgentConfig" src/utils/config_loader.py
```

If `AgentConfig` is not exported at that path, adjust the import in the endpoint accordingly (may need `from src.models import AgentConfig` or it's defined inline in config_loader — use whatever the grep reveals).

- [ ] **Step 6: Run the new endpoint tests**

```bash
.venv/bin/python -m pytest tests/test_api.py -k "TestPatchSettings or TestValidateModel" -v
```

Expected: all new tests PASS.

- [ ] **Step 7: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v -x
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/api/app.py tests/test_api.py
git commit -m "feat: add PATCH /settings and POST /settings/validate-model endpoints"
```

---

## Task 5: Update `frontend/src/lib/api.ts` — new types and methods

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add `SETTINGS_CHANGE` to `ActionType` union (isolated from dropdowns)**

In `frontend/src/lib/api.ts`, update `ActionType` and add the `AuditActionType`:

```typescript
// Triage action types — used in dropdowns and action submission
export type ActionType = "CREATE_REVIEW" | "REQUEST_VERIFICATION" | "VENDOR_FOLLOW_UP" | "STORE_CHECK" | "DEFER";

// Audit-only action type — never shown in dropdowns, only in history
export type AuditActionType = "SETTINGS_CHANGE";

// Union for ActionRecord deserialization (covers both triage and audit types)
export type AnyActionType = ActionType | AuditActionType;
```

Update `ActionRecord` to use `AnyActionType`:

```typescript
export interface ActionRecord {
  request_id: string;
  exception_id: string;
  run_date: string;
  action_type: AnyActionType;   // was ActionType
  requested_by: string;
  requested_by_role: string;
  payload: Record<string, unknown>;
  status: ActionStatus;
  created_at: string;
  updated_at: string;
  failure_reason?: string | null;
  downstream_response?: Record<string, unknown> | null;
}
```

`ANALYST_ACTION_TYPES` and `PLANNER_ACTION_TYPES` remain unchanged — `SETTINGS_CHANGE` is intentionally absent from both.

- [ ] **Step 2: Add `EditableDraft`, `PatchSettingsResult`, and `ValidateModelResult` types**

Add after the `ModelList` interface:

```typescript
export interface EditableDraft {
  AGENT_PROVIDER?: string;
  AGENT_MODEL?: string;
  API_USER_ROLE?: string;
  API_USER_ROLES?: string;
  OLLAMA_BASE_URL?: string;
  BACKEND_PORT?: string;
}

export interface PatchSettingsResult {
  applied: string[];
  restart_required: string[];
  errors: Record<string, string>;
}

export interface ValidateModelResult {
  provider: string;
  model: string;
  models: string[];
  model_available: boolean;
  error?: string;
}
```

- [ ] **Step 3: Add `patchSettings` and `validateDraftModel` to the `api` object**

Add after `listModels`:

```typescript
  patchSettings: async (payload: EditableDraft): Promise<PatchSettingsResult> => {
    const res = await fetch(`${PROXY_BASE}/settings`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (res.status === 422) {
      const body = await res.json().catch(() => ({}));
      return { applied: [], restart_required: [], errors: body.errors ?? {} };
    }
    if (!res.ok) {
      throw await toApiError(res, `Failed to save settings: ${res.statusText}`);
    }
    return res.json();
  },

  validateDraftModel: async (payload: {
    provider: string;
    model: string;
    ollama_base_url?: string;
  }): Promise<ValidateModelResult> => {
    const res = await fetch(`${PROXY_BASE}/settings/validate-model`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return {
        provider: payload.provider,
        model: payload.model,
        models: [],
        model_available: false,
        error: body.detail?.error ?? body.detail ?? res.statusText,
      };
    }
    return res.json();
  },
```

- [ ] **Step 4: Run frontend type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add settings edit types and api methods to api.ts"
```

---

## Task 6: Add edit mode to `frontend/src/app/settings/page.tsx`

**Files:**
- Modify: `frontend/src/app/settings/page.tsx`

This is the largest task. Work top-down: state → header → editable rows → apply flow.

- [ ] **Step 1: Add edit-mode state and helpers at the top of `SettingsPage`**

Replace the state block in `SettingsPage` (after the existing `modelsLoading` / `error` state) with:

```typescript
  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<EditableDraft>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [applyLoading, setApplyLoading] = useState(false);
  const [applySuccess, setApplySuccess] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [restartRequired, setRestartRequired] = useState<string[]>([]);

  const isDirty = Object.keys(draft).length > 0;
  const isPlanner = settings?.current_user?.role === "planner";

  const discardEdits = () => {
    setDraft({});
    setFieldErrors({});
    setApplyError(null);
    setIsEditing(false);
  };
```

Also add the `EditableDraft`, `PatchSettingsResult` import to the `api` import line:

```typescript
import { api, AppSettings, ModelList, EditableDraft, PatchSettingsResult } from "../../lib/api";
```

- [ ] **Step 2: Add `beforeunload` guard**

Add this `useEffect` after the existing `useEffect` for `api.getSettings()`:

```typescript
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);
```

- [ ] **Step 3: Add `applyChanges` handler**

Add after the `fetchModels` function:

```typescript
  const applyChanges = async () => {
    setApplyLoading(true);
    setApplyError(null);
    try {
      const result = await api.patchSettings(draft);
      if (Object.keys(result.errors).length > 0) {
        setFieldErrors(result.errors);
        return;
      }
      setRestartRequired(result.restart_required);
      setApplySuccess(true);
      setDraft({});
      setFieldErrors({});
      setIsEditing(false);
      // Refresh read-only server fields (note: new env values only take effect after restart)
      api.getSettings().then(setSettings).catch(() => {});
    } catch (e) {
      setApplyError(e instanceof Error ? e.message : "Failed to save settings.");
    } finally {
      setApplyLoading(false);
    }
  };
```

- [ ] **Step 4: Replace the header JSX with edit-mode-aware version**

Replace the `<header>` block inside the return statement:

```tsx
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/60 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-100">Settings</h1>
            <p className="text-xs text-slate-500 mt-0.5">Runtime configuration — read from .env and config.yaml</p>
          </div>
          <div className="flex items-center gap-2">
            {!isEditing ? (
              <>
                <Link
                  href="/"
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
                >
                  ← Dashboard
                </Link>
                <button
                  onClick={() => { setIsEditing(true); setApplySuccess(false); }}
                  disabled={!isPlanner}
                  title={isPlanner ? undefined : "Planner role required"}
                  className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Edit Settings
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={discardEdits}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-rose-400 hover:text-rose-300"
                >
                  Discard
                </button>
                <button
                  onClick={applyChanges}
                  disabled={!isDirty || applyLoading || Object.keys(fieldErrors).length > 0}
                  className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {applyLoading ? "Saving…" : "Apply Changes"}
                </button>
              </>
            )}
          </div>
        </div>
        {isEditing && (
          <div className="bg-amber-500/10 border-b border-amber-500/20 px-6 py-2">
            <p className="text-xs text-amber-300 max-w-3xl mx-auto">
              You are editing settings — unsaved changes will be lost if you navigate away. Saved changes take effect after backend restart.
            </p>
          </div>
        )}
      </header>
```

- [ ] **Step 5: Add success and error toasts just below the header, before `<main>`**

Add between `</header>` and `<main`:

```tsx
      {applySuccess && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/20 px-6 py-3">
          <p className="text-xs text-emerald-300 max-w-3xl mx-auto">
            Settings saved to .env. Restart the backend (<code className="text-emerald-400">bash scripts/dev.sh</code>) to apply changes.
          </p>
        </div>
      )}
      {applyError && (
        <div className="bg-rose-500/10 border-b border-rose-500/20 px-6 py-3">
          <p className="text-xs text-rose-300 max-w-3xl mx-auto">{applyError}</p>
        </div>
      )}
```

- [ ] **Step 6: Replace the AI Provider section with edit-aware version**

Replace the entire `<Section title="AI Provider">` block:

```tsx
        {/* LLM Provider */}
        <Section title="AI Provider">
          {/* Provider */}
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Provider</p>
              <p className="text-xs text-slate-500 mt-0.5">Set AGENT_PROVIDER in .env to switch. Options: claude · openai · gemini · ollama</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <select
                    value={draft.AGENT_PROVIDER ?? effectiveProvider}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, AGENT_PROVIDER: e.target.value, AGENT_MODEL: undefined }));
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.AGENT_PROVIDER; return n; });
                    }}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1"
                  >
                    {["claude", "openai", "gemini", "ollama"].map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.AGENT_PROVIDER && <p className="text-xs text-rose-400">{fieldErrors.AGENT_PROVIDER}</p>}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-emerald-300">{effectiveProvider}</span>
                  {s.env_overrides.AGENT_PROVIDER && <Badge text="env override" variant="warn" />}
                </div>
              )}
            </div>
          </div>

          {/* Model */}
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Model</p>
              <p className="text-xs text-slate-500 mt-0.5">Set AGENT_MODEL in .env. Use &apos;Verify Available Models&apos; below to find valid names.</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={draft.AGENT_MODEL ?? effectiveModel}
                      onChange={(e) => {
                        setDraft((d) => ({ ...d, AGENT_MODEL: e.target.value }));
                        setFieldErrors((fe) => { const n = { ...fe }; delete n.AGENT_MODEL; return n; });
                      }}
                      className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-56"
                    />
                    <button
                      onClick={async () => {
                        const draftProvider = draft.AGENT_PROVIDER ?? effectiveProvider;
                        const draftModel = draft.AGENT_MODEL ?? effectiveModel;
                        const result = await api.validateDraftModel({ provider: draftProvider, model: draftModel, ollama_base_url: draft.OLLAMA_BASE_URL });
                        if (result.error || !result.model_available) {
                          setFieldErrors((fe) => ({ ...fe, AGENT_MODEL: result.error ?? `Model not found for provider ${draftProvider}` }));
                        } else {
                          setFieldErrors((fe) => { const n = { ...fe }; delete n.AGENT_MODEL; return n; });
                        }
                      }}
                      className="rounded bg-slate-700 border border-slate-600 text-slate-300 text-xs px-2 py-1 hover:border-blue-400 hover:text-blue-300"
                    >
                      Verify
                    </button>
                  </div>
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.AGENT_MODEL && <p className="text-xs text-rose-400">{fieldErrors.AGENT_MODEL}</p>}
                </div>
              ) : (
                <div className="flex flex-col items-end gap-1">
                  <span className="font-mono text-emerald-300">{effectiveModel}</span>
                  {s.env_overrides.AGENT_MODEL && <Badge text="env override" variant="warn" />}
                  {modelList?.current_model_available === false && <Badge text="⚠ model not found" variant="error" />}
                  {modelList?.current_model_available === true && <Badge text="✓ confirmed available" variant="ok" />}
                </div>
              )}
            </div>
          </div>

          <SettingRow
            label="API Key Env Var"
            value={<Badge text={PROVIDER_KEY_ENV[provider] ?? "—"} />}
            hint="Set this in your .env file. Keys are never transmitted to the UI."
          />
          {/* Ollama URL — show in read mode when provider=ollama; always show in edit mode */}
          {(provider === "ollama" || isEditing) && (
            <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60 last:border-0">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-300">Ollama Base URL</p>
                <p className="text-xs text-slate-500 mt-0.5">Set OLLAMA_BASE_URL in .env to change.</p>
              </div>
              <div className="text-right">
                {isEditing ? (
                  <div className="flex flex-col items-end gap-1">
                    <input
                      type="text"
                      value={draft.OLLAMA_BASE_URL ?? s.agent.ollama_base_url}
                      onChange={(e) => {
                        setDraft((d) => ({ ...d, OLLAMA_BASE_URL: e.target.value }));
                        setFieldErrors((fe) => { const n = { ...fe }; delete n.OLLAMA_BASE_URL; return n; });
                      }}
                      className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-56"
                    />
                    <Badge text="⚠ restart required" variant="warn" />
                    {fieldErrors.OLLAMA_BASE_URL && <p className="text-xs text-rose-400">{fieldErrors.OLLAMA_BASE_URL}</p>}
                  </div>
                ) : (
                  <span className="font-mono text-emerald-300">{s.agent.ollama_base_url}</span>
                )}
              </div>
            </div>
          )}

          {/* Verify models button — read mode only */}
          {!isEditing && (
            <div className="pt-2 flex flex-wrap gap-2">
              <button
                onClick={fetchModels}
                disabled={modelsLoading}
                className="rounded-lg bg-blue-600/80 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {modelsLoading ? "Loading…" : "Verify Available Models"}
              </button>
              {PROVIDER_DOCS[provider] && (
                <a
                  href={PROVIDER_DOCS[provider]}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
                >
                  View Model Docs ↗
                </a>
              )}
            </div>
          )}

          {/* Model list results — read mode only */}
          {!isEditing && modelList && (
            <div className="mt-3 rounded-lg border border-slate-700/60 bg-slate-900/50 p-4 space-y-2">
              {modelList.error && <p className="text-xs text-rose-400">{modelList.error}</p>}
              {modelList.models.length > 0 ? (
                <>
                  <p className="text-xs text-slate-400 mb-2">
                    {modelList.models.length} models available — copy the exact ID to <code className="text-emerald-400">AGENT_MODEL</code> in your .env:
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 max-h-48 overflow-y-auto">
                    {modelList.models.map((m) => (
                      <div
                        key={m}
                        className={`flex items-center gap-2 rounded px-2 py-1 text-xs font-mono ${
                          m === effectiveModel
                            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        {m === effectiveModel && <span>✓</span>}
                        {m}
                      </div>
                    ))}
                  </div>
                </>
              ) : !modelList.error ? (
                <p className="text-xs text-slate-500">No models returned — provider may not support listing.</p>
              ) : null}
            </div>
          )}
        </Section>
```

- [ ] **Step 7: Replace the Server section with edit-aware version**

Replace the `<Section title="Server">` block:

```tsx
        {/* Server */}
        <Section title="Server">
          {/* Backend Port */}
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Backend Port</p>
              <p className="text-xs text-slate-500 mt-0.5">Set BACKEND_PORT in .env. Requires restart.</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <input
                    type="number"
                    min={1024}
                    max={65535}
                    value={draft.BACKEND_PORT ?? s.env_overrides.BACKEND_PORT}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, BACKEND_PORT: e.target.value }));
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.BACKEND_PORT; return n; });
                    }}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-28"
                  />
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.BACKEND_PORT && <p className="text-xs text-rose-400">{fieldErrors.BACKEND_PORT}</p>}
                </div>
              ) : (
                <span className="font-mono text-emerald-300">{s.env_overrides.BACKEND_PORT}</span>
              )}
            </div>
          </div>
          <SettingRow
            label="API User"
            value={s.current_user.username}
            mono
            hint="HTTP Basic Auth username (API_USERNAME in .env, default: admin)."
          />
          <SettingRow
            label="Your Role"
            value={
              <Badge
                text={s.current_user.role}
                variant={s.current_user.role === "planner" ? "ok" : "default"}
              />
            }
            hint="Set API_USER_ROLES=username:role in .env. Planners can approve overrides and use additional action types."
          />
        </Section>
```

- [ ] **Step 8: Replace the User Roles section with edit-aware version**

Replace the `{Object.keys(s.user_roles).length > 0 && (...)}` block:

```tsx
        {/* User Roles */}
        <Section title="User Roles">
          <div className="flex items-start justify-between gap-4 py-3 border-b border-slate-800/60 last:border-0">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Role Mappings</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Comma-separated <code className="text-emerald-400">username:role</code> pairs (API_USER_ROLES). Each role must be analyst or planner.
              </p>
            </div>
            <div className="text-right min-w-[220px]">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <textarea
                    rows={3}
                    value={
                      draft.API_USER_ROLES !== undefined
                        ? draft.API_USER_ROLES.split(",").map((s) => s.trim()).filter(Boolean).join("\n")
                        : Object.entries(s.user_roles).map(([u, r]) => `${u}:${r}`).join("\n")
                    }
                    onChange={(e) => {
                      const csv = e.target.value.split("\n").map((l) => l.trim()).filter(Boolean).join(",");
                      setDraft((d) => ({ ...d, API_USER_ROLES: csv }));
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.API_USER_ROLES; return n; });
                    }}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1 w-56 resize-none"
                    placeholder={"alice:planner\nbob:analyst"}
                  />
                  <div className="flex gap-1 flex-wrap justify-end">
                    <Badge text="⚠ restart required" variant="warn" />
                    {/* Also show select for default role */}
                  </div>
                  {fieldErrors.API_USER_ROLES && <p className="text-xs text-rose-400">{fieldErrors.API_USER_ROLES}</p>}
                </div>
              ) : (
                <div className="flex flex-col items-end gap-1">
                  {Object.keys(s.user_roles).length > 0
                    ? Object.entries(s.user_roles).map(([user, role]) => (
                        <div key={user} className="flex items-center gap-2">
                          <span className="text-xs text-slate-400 font-mono">{user}</span>
                          <Badge text={role} variant={role === "planner" ? "ok" : "default"} />
                        </div>
                      ))
                    : <span className="text-xs text-slate-500">No mappings set</span>
                  }
                </div>
              )}
            </div>
          </div>

          {/* Default role */}
          <div className="flex items-start justify-between gap-4 py-3 last:border-0">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-300">Default Role</p>
              <p className="text-xs text-slate-500 mt-0.5">Applied to any user not listed above (API_USER_ROLE).</p>
            </div>
            <div className="text-right">
              {isEditing ? (
                <div className="flex flex-col items-end gap-1">
                  <select
                    value={draft.API_USER_ROLE ?? s.current_user.role}
                    onChange={(e) => {
                      setDraft((d) => ({ ...d, API_USER_ROLE: e.target.value }));
                      setFieldErrors((fe) => { const n = { ...fe }; delete n.API_USER_ROLE; return n; });
                    }}
                    className="rounded bg-slate-800 border border-slate-600 text-emerald-300 text-sm font-mono px-2 py-1"
                  >
                    <option value="analyst">analyst</option>
                    <option value="planner">planner</option>
                  </select>
                  <Badge text="⚠ restart required" variant="warn" />
                  {fieldErrors.API_USER_ROLE && <p className="text-xs text-rose-400">{fieldErrors.API_USER_ROLE}</p>}
                </div>
              ) : (
                <Badge
                  text={s.current_user.role}
                  variant={s.current_user.role === "planner" ? "ok" : "default"}
                />
              )}
            </div>
          </div>
        </Section>
```

- [ ] **Step 9: Update the "How to change these settings" hint to be edit-mode-aware**

Replace the bottom hint block:

```tsx
        {/* Bottom hint */}
        {!isEditing && (
          <div className="rounded-lg border border-slate-800/60 bg-slate-900/30 p-4 space-y-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">How to change these settings</p>
            <p className="text-xs text-slate-400">
              Click <strong className="text-slate-300">Edit Settings</strong> above (planner role required), or edit{" "}
              <code className="text-emerald-400">.env</code> in the repo root and restart the backend with{" "}
              <code className="text-emerald-400">bash scripts/dev.sh</code>.
              Changes to <code className="text-emerald-400">config/config.yaml</code> also require a restart.
            </p>
          </div>
        )}
```

- [ ] **Step 10: Run type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no type errors. Fix any that appear (typically `draft.AGENT_MODEL` being `string | undefined` where `string` is expected — use `?? ""` coercion as needed).

- [ ] **Step 11: Start the dev stack and manually verify**

```bash
bash scripts/dev.sh
```

Open http://localhost:3000/settings.

Verify as **analyst** (default role):
- "Edit Settings" button is visible but greyed out with tooltip "Planner role required"

Change `API_USER_ROLE=planner` in `.env` and restart. Verify as **planner**:
- "Edit Settings" enters edit mode
- Amber banner appears
- All six fields show inputs
- All fields show "⚠ restart required"
- Changing provider to `openai` clears the model field
- "Verify" button on model field calls validate-model
- "Apply Changes" disabled until a field is changed
- "Discard" resets and exits edit mode
- Successful apply shows green toast and exits edit mode

- [ ] **Step 12: Commit**

```bash
git add frontend/src/app/settings/page.tsx
git commit -m "feat: add planner-gated edit mode to Settings page"
```

---

## Task 7: Final regression check and push

- [ ] **Step 1: Run full backend test suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend test suite**

```bash
cd frontend && npm test -- --watchAll=false
```

Expected: all tests pass. (ActionModal and ExceptionCard tests should be unaffected since `SETTINGS_CHANGE` is absent from both action type arrays.)

- [ ] **Step 3: Run frontend type-check one final time**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit any remaining changes and push**

```bash
git push origin main
```
