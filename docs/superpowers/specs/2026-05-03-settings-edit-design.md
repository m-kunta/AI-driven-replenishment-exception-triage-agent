# Settings Edit Design

**Date:** 2026-05-03
**Status:** Approved
**Scope:** Add planner-gated, staged edit mode to the Settings page, backed by a new `PATCH /settings` endpoint that writes `.env` in-place and logs changes to the action audit trail.

---

## 1. Goals

- Allow planners to change runtime settings from the UI without touching files directly.
- Block all writes for analysts (read-only view, same as today).
- Never expose or store secret values (API keys, passwords, webhook URLs).
- Record every settings change in the existing `actions.db` audit log.
- Leave a clean extension point for a future `admin` role.

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
| `AGENT_PROVIDER` | No |
| `AGENT_MODEL` | No |
| `API_USER_ROLE` | No |
| `API_USER_ROLES` | No |
| `OLLAMA_BASE_URL` | No |
| `BACKEND_PORT` | Yes |

Any key outside this list in a `PATCH` payload is rejected `422` — even from a planner. This is defense in depth against crafted requests bypassing the UI.

**Per-field validation rules:**

| Key | Rule |
|---|---|
| `AGENT_PROVIDER` | Must be one of `claude`, `openai`, `gemini`, `ollama` |
| `AGENT_MODEL` | Must be non-empty; validated against `provider.list_models()` unless provider is `ollama` |
| `API_USER_ROLE` | Must be `analyst` or `planner` |
| `API_USER_ROLES` | Comma-separated `username:role` pairs; each role must be `analyst` or `planner` |
| `OLLAMA_BASE_URL` | Must be a valid URL starting with `http://` or `https://` |
| `BACKEND_PORT` | Integer 1024–65535 |

**Write strategy:** read existing `.env` line-by-line, update matching `KEY=value` lines in-place, preserve comments and ordering, write to a temp file, then `os.replace()` (atomic on POSIX). The `.env` file path is resolved relative to the repo root, same as `dev.sh`.

**Return shape:**

```json
{
  "applied": ["AGENT_PROVIDER", "AGENT_MODEL"],
  "restart_required": ["BACKEND_PORT"],
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
3. **Audit** — for each applied key write one `ActionRecord` to `actions.db`:
   - `action_type = "SETTINGS_CHANGE"`
   - `details = { "key": "<KEY>", "restart_required": true|false }`
   - `requested_by = username`
   - `requested_by_role = "planner"`
   - No old or new values stored — audit records *that* a change happened, not *what* the value was.

**Extension point:** the endpoint accepts a `required_role: str = "planner"` parameter. When an `admin` role is introduced, the guard becomes `role in {required_role, "admin"}` with no structural change.

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
- Amber banner below header: "You are editing settings — unsaved changes will be lost if you navigate away."
- `← Dashboard` link replaced by a confirmation button ("Discard changes and leave?").
- `beforeunload` listener registered while `isDirty`.

### 4.3 Editable field inputs

| Field | Component | Notes |
|---|---|---|
| `AGENT_PROVIDER` | `<select>` | Options: `claude`, `openai`, `gemini`, `ollama`. Changing provider clears `AGENT_MODEL` draft. |
| `AGENT_MODEL` | `<input>` + inline "Verify" button | Calls `GET /models` on demand; marks field error if model not in list. |
| `API_USER_ROLE` | `<select>` | Options: `analyst`, `planner`. |
| `API_USER_ROLES` | `<textarea>` | One `username:role` per line for readability; serialised to comma-separated on submit. Client-side parse-on-blur validation. |
| `OLLAMA_BASE_URL` | `<input>` | Shown only when provider (draft or current) is `ollama`. |
| `BACKEND_PORT` | `<input type="number">` | Inline "⚠ Restart required" badge always visible for this field in edit mode. |

Pipeline Behaviour fields (`batch_size`, `max_tokens`, `retry_attempts`) render read-only in both modes.

### 4.4 Apply flow

1. "Apply Changes" clicked → spinner, inputs locked.
2. `PATCH /settings` called with `draft` (only changed keys).
3. **Success (`200`):**
   - If `restart_required` is non-empty: show persistent amber toast "Settings saved. Restart the backend for port changes to take effect."
   - Else: show green toast "Settings saved."
   - Fetch fresh `GET /settings`, update `settings` state, clear `draft`, exit edit mode.
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

---

## 5. Audit Log Integration

`action_type = "SETTINGS_CHANGE"` is added to the existing action type enum. The Action History page already displays all action types generically, so no UI changes are needed there — the new entries will appear automatically with their `key` detail visible in the details column.

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

---

## 7. Files Affected

| File | Change |
|---|---|
| `src/api/env_writer.py` | New — `EnvWriter` class |
| `src/api/app.py` | Add `PATCH /settings` endpoint |
| `src/models.py` | Add `SETTINGS_CHANGE` to action type enum |
| `frontend/src/lib/api.ts` | Add `patchSettings`, `EditableDraft`, `PatchSettingsResult` types |
| `frontend/src/app/settings/page.tsx` | Add edit mode toggle, draft state, editable inputs, apply flow |
| `tests/test_api.py` | Tests for `PATCH /settings` — validation, write, role guard, audit |
