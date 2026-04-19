# Analyst Override Schema Design

**Date:** 2026-04-19  
**Phase:** 12 — Active Learning  
**Scope:** SQLite schema and `OverrideStore` module for storing analyst override decisions and feeding approved examples into the few-shot prompt injection pipeline.

---

## Problem Statement

The AI triage pipeline produces `TriageResult` records (priority, root_cause, recommended_action, etc.). Analysts reviewing the dashboard may disagree with the AI's decisions. We need to capture those corrections, gate them through a buyer approval workflow, and surface approved overrides as few-shot examples in the next pipeline run to improve AI output over time.

---

## Schema

### Table: `analyst_overrides`

```sql
CREATE TABLE IF NOT EXISTS analyst_overrides (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_id                    TEXT    NOT NULL,
    run_date                        TEXT    NOT NULL,
    analyst_username                TEXT    NOT NULL,
    submitted_at                    TEXT    NOT NULL,

    -- Corrected output fields (all nullable; at least one must be non-null)
    override_priority               TEXT,
    override_root_cause             TEXT,
    override_recommended_action     TEXT,
    override_financial_impact_statement TEXT,
    override_planner_brief          TEXT,
    override_compounding_risks      TEXT,   -- JSON array serialized as text
    analyst_note                    TEXT,

    -- Full EnrichedExceptionSchema snapshot for few-shot input reconstruction
    enriched_input_snapshot         TEXT    NOT NULL,

    -- Approval workflow
    approval_status                 TEXT    NOT NULL DEFAULT 'pending'
                                            CHECK (approval_status IN ('pending','approved','rejected')),
    approved_by                     TEXT,
    approved_at                     TEXT,
    auto_approved                   INTEGER NOT NULL DEFAULT 0,
    rejected_by                     TEXT,
    rejected_at                     TEXT,
    rejection_reason                TEXT
);

CREATE INDEX IF NOT EXISTS idx_overrides_exception_id
    ON analyst_overrides (exception_id);

CREATE INDEX IF NOT EXISTS idx_overrides_run_date
    ON analyst_overrides (run_date);

CREATE INDEX IF NOT EXISTS idx_overrides_approval_status_submitted
    ON analyst_overrides (approval_status, submitted_at);
```

**Column notes:**

| Column | Details |
|---|---|
| `exception_id` | Matches `TriageResult.exception_id` from the pipeline output |
| `run_date` | YYYY-MM-DD string — identifies which pipeline run the exception came from |
| `analyst_username` | Pulled from the HTTP Basic Auth session at override submission time |
| `submitted_at` | ISO-8601 UTC string (`2026-04-19T14:32:00Z`) |
| `override_*` fields | Any subset of corrected TriageResult output fields; at least one must be non-null |
| `override_compounding_risks` | JSON array serialized as text, e.g. `'["promo_overlap", "vendor_late"]'` |
| `analyst_note` | Free-form reasoning from the analyst; captured for audit and learning context |
| `enriched_input_snapshot` | Full `EnrichedExceptionSchema` as JSON — stored at submission time so the input is immutable even if source files are regenerated |
| `approval_status` | One of: `pending`, `approved`, `rejected` |
| `approved_by` | Analyst/buyer username, or `'auto'` for TTL-triggered auto-approval |
| `auto_approved` | `1` if promoted by the 1-day TTL rule; `0` if manually approved or still pending |
| `rejected_by` | Username of the buyer who rejected the override |
| `rejected_at` | ISO-8601 UTC timestamp of rejection |
| `rejection_reason` | Optional free-text reason captured at rejection time for audit |

---

## Module Structure

### New files

```
src/
└── db/
    ├── __init__.py          # exports OverrideStore
    ├── store.py             # OverrideStore class
    └── schema.sql           # CREATE TABLE + indexes DDL

data/schema/
└── analyst_overrides_schema.sql   # same DDL mirrored for reference

tests/
└── test_db_store.py         # in-memory SQLite tests
```

### DB file location

`output/overrides.db` — consistent with where output artifacts live. Added to `.gitignore`.

`OverrideStore.__init__` creates the `output/` parent directory if it does not exist before opening the DB connection.

---

## `OverrideStore` API

```python
class OverrideStore:
    def __init__(self, db_path: str = "output/overrides.db") -> None:
        """Opens (or creates) the SQLite DB, runs CREATE TABLE IF NOT EXISTS, enables WAL mode."""

    def insert_override(
        self,
        exception_id: str,
        run_date: str,
        analyst_username: str,
        enriched_input_snapshot: dict,
        override_priority: str | None = None,
        override_root_cause: str | None = None,
        override_recommended_action: str | None = None,
        override_financial_impact_statement: str | None = None,
        override_planner_brief: str | None = None,
        override_compounding_risks: list[str] | None = None,
        analyst_note: str | None = None,
    ) -> int:
        """Inserts a new override row. Raises ValueError if no override_* field is set. Returns inserted row id."""

    def approve_override(self, override_id: int, approved_by: str) -> None:
        """Sets approval_status='approved', approved_by, approved_at on a pending row."""

    def reject_override(self, override_id: int, rejected_by: str, reason: str | None = None) -> None:
        """Sets approval_status='rejected', rejected_by, rejected_at, rejection_reason. Rows are retained for audit."""

    def auto_approve_pending(self) -> int:
        """Promotes all pending overrides older than 1 day to approved (auto_approved=1). Returns count promoted."""

    def get_approved_few_shot_examples(self, limit: int = 10) -> list[dict]:
        """Returns up to `limit` approved overrides as {input: dict, output: dict} pairs.

        Ordered by submitted_at DESC. Stratified across override_priority values so no single
        priority dominates the few-shot pool — up to ceil(limit/4) rows per priority bucket,
        filled from remaining buckets if a bucket has fewer rows than its allocation.
        Returns [] if no approved rows exist; prompt_composer falls back to static prompts/examples.
        """
```

**`get_approved_few_shot_examples` output shape:**
```json
[
  {
    "input": { /* full EnrichedExceptionSchema fields */ },
    "output": {
      "priority": "CRITICAL",
      "root_cause": "...",
      "recommended_action": "...",
      "financial_impact_statement": "...",
      "planner_brief": "...",
      "compounding_risks": ["promo_overlap"]
    }
  }
]
```
Only non-null override fields are included in `output`. This list is passed directly to `prompt_composer.py` for few-shot block injection. When the list is empty, `prompt_composer` falls back silently to its existing static few-shot examples in `prompts/`.

---

## Auto-Approval TTL

`auto_approve_pending()` runs a single UPDATE:

```sql
UPDATE analyst_overrides
SET approval_status = 'approved',
    approved_by     = 'auto',
    approved_at     = :now,
    auto_approved   = 1
WHERE approval_status = 'pending'
  AND submitted_at   <= :cutoff  -- cutoff = now - 1 day
```

Called once at pipeline startup in `src/main.py` — no background thread or cron.

**Semantic note:** "auto-approved after 1 day" means "auto-approved on the next pipeline run that occurs ≥1 day after submission." If the pipeline runs every 3 days, an override will be promoted on that run, not exactly 24 hours after submission.

---

## Error Handling & Constraints

- `insert_override()` raises `ValueError` if all `override_*` fields (including `analyst_note`) are null — an empty override with no correction and no commentary is meaningless. An `analyst_note`-only override (no field corrections) is valid.
- `enriched_input_snapshot` is serialized using `model.model_dump(mode='json')` — this ensures `date` and `datetime` fields are serialized as ISO strings, not Python objects, making the JSON round-trippable.
- `run_date` is validated as an ISO date string (`YYYY-MM-DD`) at `insert_override()` time; invalid formats raise `ValueError`.
- Multiple overrides for the same `exception_id` are permitted (analysts can revise). When multiple approved overrides exist for the same `exception_id`, all are eligible as few-shot examples — the stratified sampler in `get_approved_few_shot_examples` naturally limits duplication via the per-priority cap.
- Approved overrides older than 90 days are excluded from `get_approved_few_shot_examples` to prevent stale examples from skewing the LLM. Older rows remain in the table for audit.
- WAL mode (`PRAGMA journal_mode=WAL`) is set on every connection open — safe for concurrent reads from the API server while the pipeline writes.
- Overrides are **append-only**. Rejected rows stay in the table with `approval_status='rejected'` for full audit trail.
- `OverrideStore` does not manage transactions externally — each public method commits atomically.
- Schema versioning: v1 is established by this spec. Future column additions use `ALTER TABLE ... ADD COLUMN` migrations; no migration framework is needed at this scale.

---

## Testing Strategy

`tests/test_db_store.py` uses an in-memory `:memory:` SQLite DB (passed via `db_path=":memory:"`):

| Test | What it verifies |
|---|---|
| `test_insert_override` | Row inserted, id returned, fields round-trip correctly |
| `test_insert_override_no_fields_raises` | `ValueError` raised when all override fields are null |
| `test_approve_override` | Status transitions to `approved`, `approved_by` set |
| `test_reject_override` | Status transitions to `rejected`, row not deleted, rejection_reason stored |
| `test_auto_approve_pending` | Rows older than 1 day promoted; fresh rows untouched |
| `test_get_approved_few_shot_examples` | Returns correct shape; only approved rows; limit respected |
| `test_get_approved_few_shot_examples_empty` | Returns `[]` when no approved rows exist |
| `test_get_approved_few_shot_examples_stratified` | No single priority dominates beyond ceil(limit/4) |
| `test_get_approved_few_shot_examples_90day_cutoff` | Rows older than 90 days excluded |
| `test_duplicate_exception_id_allowed` | Multiple overrides for same exception_id are permitted |
| `test_insert_override_invalid_run_date` | `ValueError` raised for non-ISO run_date format |
| `test_insert_override_analyst_note_only` | Override with only analyst_note (no field corrections) is accepted |

---

## Integration Points (Future Phases)

- **`src/api/app.py`** — new endpoints `POST /overrides`, `GET /overrides`, `POST /overrides/{id}/approve`, `POST /overrides/{id}/reject` will import and use `OverrideStore`
- **`src/agent/prompt_composer.py`** — `get_approved_few_shot_examples()` feeds into the few-shot JSON block injected into the LLM prompt at construction time
- **`src/main.py`** — calls `auto_approve_pending()` at pipeline startup
