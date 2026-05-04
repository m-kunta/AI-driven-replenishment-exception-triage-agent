# Settings Edit Design

**Date:** 2026-05-03
**Status:** Approved
**Scope:** Add planner-gated, staged edit mode to the Settings page, backed by a new `PATCH /settings` endpoint that writes `.env` in-place for the next backend start and logs changes to the action audit trail.

---

## 1. Goals

- Allow planners to change runtime settings from the UI without touching files directly.
- Block all writes for analysts (read-only view, same as today).
- Never expose or store secret values (API keys, passwords, webhook URLs).
- Record every settings change in the existing `actions.db` audit log.
- Leave a clean extension point for a future `admin` role.
- Be explicit that `.env` edits are persisted immediately but only take effect after backend restart in the current architecture.

## 2. Out of Scope

- `config.yaml` pipeline tuning fields (`batch_size`, `max_tokens`, `retry_attempts`) — these remain read-only in this phase.
- Credential fields: `API_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `*_WEBHOOK_URL`, `*_EMAIL`, `DB_CONNECTION_STRING`. File-only forever.
- Server restart triggering — the UI notifies but does not restart the process.
- Multi-user / persisted draft state — drafts are session-only React state.

---

## 3. Backend

### 3.1 `EnvWriter` — `src/api/env_writer.py`

New utility class with a single responsibility: safe, atomic `.env` mutation.

**Allowlist** (the only keys `PATCH /settings` will ever touch):

| Key | Restart required |
|---|---|
| `AGENT_PROVIDER` | Yes |
| `AGENT_MODEL` | Yes |
| `API_USER_ROLE` | Yes |
| `API_USER_ROLES` | Yes |
| `OLLAMA_BASE_URL` | Yes (requires config_loader.py env override — see §3.4) |
| `BACKEND_PORT` | Yes |

Any key outside this list in a `PATCH` payload is rejected `422` — even from a planner. This is defense in depth against crafted requests bypassing the UI.

**Runtime effect:** every allowlisted key is treated as **restart required** in this phase. The running FastAPI process reads these values from `os.environ` at startup and does not re-load `.env` dynamically. `PATCH /settings` persists edits for the next process start; it does not mutate the current process environment.

**Per-field validation rules:**

| Key | Rule |
|---|---|
| `AGENT_PROVIDER` | Must be one of `claude`, `openai`, `gemini`, `ollama` |
| `AGENT_MODEL` | Must be non-empty; if model verification succeeds, the submitted model must appear in the returned list for the submitted provider. If verification cannot complete, reject with a provider-specific error and write nothing. |
| `API_USER_ROLE` | Must be `analyst` or `planner` |
| `API_USER_ROLES` | Comma-separated `username:role` pairs; each role must be `analyst` or `planner` |
| `OLLAMA_BASE_URL` | Must be a valid URL starting with `http://` or `https://` |
| `BACKEND_PORT` | Integer 1024–65535 |

**Write strategy:** read existing `.env` line-by-line, update matching `KEY=value` lines in-place, preserve comments and ordering, append any missing allowlisted keys at the end of the file, write to a temp file, then `os.replace()` (atomic on POSIX). The `.env` file path is resolved relative to the repo root, same as `dev.sh`.

**Return shape:**

```json
{
  "applied": ["AGENT_PROVIDER", "AGENT_MODEL"],
  "restart_required": ["AGENT_PROVIDER", "AGENT_MODEL"],
  "errors": {}
}
```

On validation failure (before any write):

```json
{
  "applied": [],
  "restart_required": [],
  "errors": {
    "AGENT_MODEL": "Model 'claude-fake-v99' not found for provider claude"
  }
}
```

### 3.2 `PATCH /settings` endpoint

```
PATCH /settings
Auth: HTTP Basic (existing get_current_username dependency)
Role guard: get_current_user_role(username) == "planner" → 403 otherwise
Body: { [key: string]: string }  (partial — only changed keys)
```

Three-phase execution:

1. **Validate** — call `EnvWriter.validate(payload)`. Return `422` with error map if any field fails.
2. **Write** — call `EnvWriter.apply(payload)`. Atomic file write.
3. **Audit** — for each applied key write one record directly to `actions.db` via `ActionStore.insert_action()`. Because `insert_action()` hardcodes `status = 'queued'`, a `status` parameter (defaulting to `'queued'` for backward compatibility) must be added to that method so settings audit records can be inserted with `status = 'completed'`. Fields:
   - `action_type = "SETTINGS_CHANGE"`
   - `payload = { "key": "<KEY>", "restart_required": true }`
   - `status = "completed"` (write is already done at this point)
   - `requested_by = username`
   - `requested_by_role = "planner"`
   - `request_id` is generated server-side per changed key, `exception_id = "__settings__"`, and `run_date` is the current local date.
   - No old or new values stored — audit records *that* a change happened, not *what* the value was.

`PATCH /settings` is a persistence endpoint, not a live-reload endpoint. A successful response means the next backend start will pick up the new values from `.env`.

**Extension point:** the endpoint accepts a `required_role: str = "planner"` parameter. When an `admin` role is introduced, the guard becomes `role in {required_role, "admin"}` with no structural change.

### 3.3 Model verification contract

The current `GET /models` endpoint validates only the provider configured in the running process, which is not sufficient for draft edits. This phase therefore adds a draft-aware verification path:

```
POST /settings/validate-model
Auth: HTTP Basic
Role guard: same as PATCH /settings
Body: {
  "provider": "claude" | "openai" | "gemini" | "ollama",
  "model": "<candidate model id>",
  "ollama_base_url"?: "<url when provider=ollama>"
}
```

Response:

```json
{
  "provider": "openai",
  "model": "gpt-4.1",
  "models": ["gpt-4.1", "gpt-4.1-mini"],
  "model_available": true
}
```

Rules:

- Validation is performed against the submitted draft provider, not the currently running provider.
- For `ollama`, validation uses the submitted `ollama_base_url` when present, otherwise the current configured base URL.
- If provider model enumeration fails, return a non-200 response with a user-safe error and do not allow `PATCH /settings` to proceed with that model.
- Existing `GET /models` remains for read-only Settings inspection of the currently running backend.

### 3.4 `OLLAMA_BASE_URL` env override in `config_loader.py`

`OLLAMA_BASE_URL` is currently read only from `config/config.yaml` — there is no `os.environ` override path for it, unlike `AGENT_PROVIDER` and `AGENT_MODEL`. Writing it to `.env` would therefore have no runtime effect unless `config_loader.py` is extended.

This phase adds an env override for `OLLAMA_BASE_URL` to `config_loader.py`, following the same pattern as the existing provider and model overrides:

```python
ollama_base_url_override = os.environ.get("OLLAMA_BASE_URL", "").strip()
if ollama_base_url_override:
    agent_cfg["ollama_base_url"] = ollama_base_url_override
```

This change is required for `EnvWriter` writes to `OLLAMA_BASE_URL` to have any effect. Without it the key must be removed from the editable allowlist.

**Files affected by this addition:** `src/utils/config_loader.py`, `tests/test_api.py` (verify env override takes effect).

---

## 4. Frontend

### 4.1 State

```ts
const [isEditing, setIsEditing] = useState(false);
const [draft, setDraft] = useState<EditableDraft>({});   // only touched keys
const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
const [applyError, setApplyError] = useState<string | null>(null);
const [restartRequired, setRestartRequired] = useState<string[]>([]);
```

`EditableDraft` covers only the six allowlisted keys. `isDirty` is `Object.keys(draft).length > 0`.

### 4.2 Edit mode toggle

**Header — read mode:**
- Blue "Edit Settings" button for planners.
- Greyed-out "Edit Settings" with tooltip "Planner role required" for analysts.
- Role derived from `settings.current_user.role` (server-authoritative, not a build-time flag).

**Header — edit mode:**
- "Apply Changes" button (blue, disabled until `isDirty` and no `fieldErrors`).
- "Discard" button (slate, always active — resets draft and exits edit mode).
- Amber banner below header: "You are editing settings — unsaved changes will be lost if you navigate away. Saved changes take effect after backend restart."
- `← Dashboard` link replaced by a confirmation button ("Discard changes and leave?").
- `beforeunload` listener registered while `isDirty`.

### 4.3 Editable field inputs

| Field | Component | Notes |
|---|---|---|
| `AGENT_PROVIDER` | `<select>` | Options: `claude`, `openai`, `gemini`, `ollama`. Changing provider clears `AGENT_MODEL` draft. |
| `AGENT_MODEL` | `<input>` + inline "Verify" button | Calls `POST /settings/validate-model` using the current draft provider/model; marks field error if model not in list or verification fails. |
| `API_USER_ROLE` | `<select>` | Options: `analyst`, `planner`. |
| `API_USER_ROLES` | `<textarea>` | One `username:role` per line for readability; serialised to comma-separated on submit. Client-side parse-on-blur validation. |
| `OLLAMA_BASE_URL` | `<input>` | Shown only when provider (draft or current) is `ollama`. |
| `BACKEND_PORT` | `<input type="number">` | Inline "Restart required" badge visible in edit mode. |

Pipeline Behaviour fields (`batch_size`, `max_tokens`, `retry_attempts`) render read-only in both modes.

All editable rows show a small "Restart required" badge in edit mode for consistency with backend behavior.

### 4.4 Apply flow

1. "Apply Changes" clicked → spinner, inputs locked.
2. `PATCH /settings` called with `draft` (only changed keys).
3. **Success (`200`):**
   - Show persistent amber toast "Settings saved to .env. Restart the backend to apply changes."
   - Do **not** assume a follow-up `GET /settings` will reflect the new effective runtime values until restart.
   - Fetch fresh `GET /settings`, update read-only server-derived fields from the response, and separately update local persisted-edit indicators from the PATCH response so the page can show "saved for next restart" even while live runtime values remain unchanged.
   - Clear `draft`, exit edit mode.
4. **Validation error (`422`):** populate `fieldErrors` from response error map. Stay in edit mode. Inputs unlocked.
5. **Auth error (`403`):** toast "Permission denied — planner role required." Exit edit mode (stale role edge case).
6. **Network / server error (`5xx`):** toast "Failed to save — try again." Stay in edit mode. Inputs unlocked.

### 4.5 `api.ts` additions

```ts
patchSettings(payload: Partial<EditableDraft>): Promise<PatchSettingsResult>
```

`PatchSettingsResult`:
```ts
{ applied: string[]; restart_required: string[]; errors: Record<string, string> }
```

Also add:

```ts
validateDraftModel(payload: {
  provider: string;
  model: string;
  ollama_base_url?: string;
}): Promise<{
  provider: string;
  model: string;
  models: string[];
  model_available: boolean;
}>
```

---

## 5. Audit Log Integration

`action_type = "SETTINGS_CHANGE"` is added to the existing action type enum. The audit event is stored through the existing `payload` column rather than a new `details` field.

Settings audit entries are **global operational events**, not exception-card events. They will therefore not appear in per-exception Action History views. In this phase, they are written to `actions.db` for traceability and future global audit surfacing, but no new frontend audit screen is required.

---

## 6. Security Summary

| Concern | Mitigation |
|---|---|
| Analyst writes settings | `PATCH /settings` enforces `role == "planner"` server-side; `403` otherwise |
| Crafted request bypasses UI allowlist | Server-side key allowlist in `EnvWriter` rejects unknown keys with `422` |
| Secret values exposed in audit log | Audit records store key name only — no values |
| Secret values editable via UI | Credential keys absent from allowlist; endpoint rejects them |
| Concurrent `.env` writes | Atomic `os.replace()` — last write wins; acceptable for single-user local tool |
| Bad config breaks backend | Hard validation before any write; nothing written on error |
| Misleading "saved means live" UX | UI consistently labels edits as "saved for next restart" and shows restart-required messaging for all editable fields |

---

## 7. Files Affected

| File | Change |
|---|---|
| `src/api/env_writer.py` | New — `EnvWriter` class |
| `src/api/app.py` | Add `PATCH /settings` and `POST /settings/validate-model` endpoints |
| `src/models.py` | Add `SETTINGS_CHANGE` to `ActionType` enum (Python) |
| `src/db/action_store.py` | Add optional `status` parameter to `insert_action()`, defaulting to `'queued'` |
| `src/utils/config_loader.py` | Add `OLLAMA_BASE_URL` env override support |
| `frontend/src/lib/api.ts` | Add `SETTINGS_CHANGE` to `ActionType` union (excluded from `ANALYST_ACTION_TYPES` and `PLANNER_ACTION_TYPES`); add `patchSettings`, `validateDraftModel`, `EditableDraft`, and response types |
| `frontend/src/app/settings/page.tsx` | Add edit mode toggle, draft state, editable inputs, restart-required messaging, and apply flow |
| `tests/test_api.py` | Tests for `PATCH /settings` and `POST /settings/validate-model` — validation, write, role guard, append-missing-key behavior, audit status, and `OLLAMA_BASE_URL` env override |
