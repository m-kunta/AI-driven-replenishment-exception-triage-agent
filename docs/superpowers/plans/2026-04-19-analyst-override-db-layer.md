# Analyst Override DB Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `src/db/` module — SQLite schema, `OverrideStore` class, and full test suite — that stores analyst override decisions and surfaces approved rows as few-shot examples for the triage LLM.

**Architecture:** Single flat `analyst_overrides` SQLite table. `OverrideStore` is a thin `sqlite3` wrapper. Approved rows are stratified by priority and capped at 90 days old before being returned as `{input, output}` pairs for prompt injection. No ORM — plain parameterized SQL throughout.

**Tech Stack:** Python 3.9+, `sqlite3` (stdlib), `pydantic` v2 (`model_dump(mode='json')`), `pytest`, `loguru`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/db/__init__.py` | Exports `OverrideStore` |
| Create | `src/db/schema.sql` | DDL for `analyst_overrides` table + indexes |
| Create | `src/db/store.py` | `OverrideStore` class (all 6 public methods) |
| Create | `data/schema/analyst_overrides_schema.sql` | Mirror of `schema.sql` for reference |
| Create | `tests/test_db_store.py` | Full test suite (12 tests, `:memory:` SQLite) |
| Modify | `.gitignore` | Add `output/overrides.db` |

---

## Task 1: Schema SQL

**Files:**
- Create: `src/db/schema.sql`
- Create: `data/schema/analyst_overrides_schema.sql`

- [ ] **Step 1: Create `src/db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS analyst_overrides (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_id                        TEXT    NOT NULL,
    run_date                            TEXT    NOT NULL,
    analyst_username                    TEXT    NOT NULL,
    submitted_at                        TEXT    NOT NULL,

    -- Corrected output fields (at least one must be non-null at insert time)
    override_priority                   TEXT,
    override_root_cause                 TEXT,
    override_recommended_action         TEXT,
    override_financial_impact_statement TEXT,
    override_planner_brief              TEXT,
    override_compounding_risks          TEXT,
    analyst_note                        TEXT,

    -- Full EnrichedExceptionSchema snapshot (model_dump(mode='json') serialized)
    enriched_input_snapshot             TEXT    NOT NULL,

    -- Approval workflow
    approval_status                     TEXT    NOT NULL DEFAULT 'pending'
                                                CHECK (approval_status IN ('pending','approved','rejected')),
    approved_by                         TEXT,
    approved_at                         TEXT,
    auto_approved                       INTEGER NOT NULL DEFAULT 0,
    rejected_by                         TEXT,
    rejected_at                         TEXT,
    rejection_reason                    TEXT
);

CREATE INDEX IF NOT EXISTS idx_overrides_exception_id
    ON analyst_overrides (exception_id);

CREATE INDEX IF NOT EXISTS idx_overrides_run_date
    ON analyst_overrides (run_date);

CREATE INDEX IF NOT EXISTS idx_overrides_approval_status_submitted
    ON analyst_overrides (approval_status, submitted_at);
```

- [ ] **Step 2: Mirror the DDL to `data/schema/analyst_overrides_schema.sql`**

Copy the exact same content from `src/db/schema.sql` to `data/schema/analyst_overrides_schema.sql`.

- [ ] **Step 3: Add `output/overrides.db` to `.gitignore`**

Open `.gitignore` and append under the `# Output` section:

```
output/overrides.db
```

- [ ] **Step 4: Commit**

```bash
git add src/db/schema.sql data/schema/analyst_overrides_schema.sql .gitignore
git commit -m "feat: add analyst_overrides DDL and update .gitignore"
```

---

## Task 2: `OverrideStore.__init__` — DB Bootstrap

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/store.py`
- Create: `tests/test_db_store.py`

- [ ] **Step 1: Create `tests/test_db_store.py` with the init test**

```python
"""Tests for OverrideStore — all use in-memory SQLite via db_path=':memory:'."""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone, timedelta
from math import ceil

from src.db.store import OverrideStore


SAMPLE_SNAPSHOT = {
    "exception_id": "EXC-001",
    "item_id": "ITM-001",
    "item_name": "Test Item",
    "store_id": "STR-001",
    "store_name": "Test Store",
    "exception_type": "OOS",
    "exception_date": "2026-04-19",
    "units_on_hand": 0,
    "days_of_supply": 0.0,
    "variance_pct": None,
    "source_system": "test",
    "batch_id": "BATCH-001",
    "ingested_at": "2026-04-19T00:00:00+00:00",
    "enrichment_confidence": "HIGH",
    "missing_data_fields": [],
}


@pytest.fixture
def store():
    return OverrideStore(db_path=":memory:")


def test_init_creates_table(store):
    cur = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='analyst_overrides'"
    )
    assert cur.fetchone() is not None


def test_init_enables_wal(store):
    cur = store._conn.execute("PRAGMA journal_mode")
    mode = cur.fetchone()[0]
    assert mode == "wal"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_db_store.py::test_init_creates_table -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `src/db/store.py` does not exist yet.

- [ ] **Step 3: Create `src/db/__init__.py`**

```python
from __future__ import annotations

from src.db.store import OverrideStore

__all__ = ["OverrideStore"]
```

- [ ] **Step 4: Create `src/db/store.py` with `__init__` only**

```python
"""SQLite-backed store for analyst override decisions (Phase 12 — Active Learning)."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Optional


class OverrideStore:
    """Thin sqlite3 wrapper for the analyst_overrides table."""

    _SCHEMA_PATH = Path(__file__).parent / "schema.sql"

    def __init__(self, db_path: str = "output/overrides.db") -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self._SCHEMA_PATH.read_text())
        self._conn.commit()
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_db_store.py::test_init_creates_table tests/test_db_store.py::test_init_enables_wal -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add src/db/__init__.py src/db/store.py tests/test_db_store.py
git commit -m "feat: add OverrideStore.__init__ with WAL mode and schema bootstrap"
```

---

## Task 3: `insert_override`

**Files:**
- Modify: `src/db/store.py`
- Modify: `tests/test_db_store.py`

- [ ] **Step 1: Add the four `insert_override` tests to `tests/test_db_store.py`**

Append to the end of the file:

```python
def _insert(store: OverrideStore, **kwargs) -> int:
    """Helper: inserts an override with sensible defaults."""
    defaults: dict = dict(
        exception_id="EXC-001",
        run_date="2026-04-19",
        analyst_username="analyst1",
        enriched_input_snapshot=SAMPLE_SNAPSHOT,
        override_priority="CRITICAL",
    )
    defaults.update(kwargs)
    return store.insert_override(**defaults)


def test_insert_override(store):
    row_id = _insert(store)
    assert isinstance(row_id, int) and row_id > 0
    row = store._conn.execute(
        "SELECT * FROM analyst_overrides WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["exception_id"] == "EXC-001"
    assert row["run_date"] == "2026-04-19"
    assert row["override_priority"] == "CRITICAL"
    assert row["approval_status"] == "pending"
    assert json.loads(row["enriched_input_snapshot"])["item_id"] == "ITM-001"


def test_insert_override_no_fields_raises(store):
    with pytest.raises(ValueError, match="At least one override field"):
        store.insert_override(
            exception_id="EXC-001",
            run_date="2026-04-19",
            analyst_username="analyst1",
            enriched_input_snapshot=SAMPLE_SNAPSHOT,
        )


def test_insert_override_invalid_run_date(store):
    with pytest.raises(ValueError, match="run_date must be YYYY-MM-DD"):
        store.insert_override(
            exception_id="EXC-001",
            run_date="yesterday",
            analyst_username="analyst1",
            enriched_input_snapshot=SAMPLE_SNAPSHOT,
            override_priority="HIGH",
        )


def test_insert_override_analyst_note_only(store):
    row_id = store.insert_override(
        exception_id="EXC-001",
        run_date="2026-04-19",
        analyst_username="analyst1",
        enriched_input_snapshot=SAMPLE_SNAPSHOT,
        analyst_note="Looks like phantom inventory — no field corrections needed.",
    )
    assert row_id > 0
    row = store._conn.execute(
        "SELECT * FROM analyst_overrides WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["analyst_note"] == "Looks like phantom inventory — no field corrections needed."
    assert row["override_priority"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -k "insert" -v
```

Expected: `AttributeError: 'OverrideStore' object has no attribute 'insert_override'`

- [ ] **Step 3: Add `insert_override` to `src/db/store.py`**

Add this method inside `OverrideStore`, after `__init__`:

```python
    def insert_override(
        self,
        exception_id: str,
        run_date: str,
        analyst_username: str,
        enriched_input_snapshot: dict,
        override_priority: Optional[str] = None,
        override_root_cause: Optional[str] = None,
        override_recommended_action: Optional[str] = None,
        override_financial_impact_statement: Optional[str] = None,
        override_planner_brief: Optional[str] = None,
        override_compounding_risks: Optional[list] = None,
        analyst_note: Optional[str] = None,
    ) -> int:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", run_date):
            raise ValueError(f"run_date must be YYYY-MM-DD, got: {run_date!r}")
        override_fields = [
            override_priority, override_root_cause, override_recommended_action,
            override_financial_impact_statement, override_planner_brief,
            override_compounding_risks, analyst_note,
        ]
        if all(f is None for f in override_fields):
            raise ValueError("At least one override field or analyst_note must be set")
        risks_json = json.dumps(override_compounding_risks) if override_compounding_risks is not None else None
        cur = self._conn.execute(
            """
            INSERT INTO analyst_overrides (
                exception_id, run_date, analyst_username, submitted_at,
                override_priority, override_root_cause, override_recommended_action,
                override_financial_impact_statement, override_planner_brief,
                override_compounding_risks, analyst_note, enriched_input_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exception_id, run_date, analyst_username,
                datetime.now(timezone.utc).isoformat(),
                override_priority, override_root_cause, override_recommended_action,
                override_financial_impact_statement, override_planner_brief,
                risks_json, analyst_note, json.dumps(enriched_input_snapshot),
            ),
        )
        self._conn.commit()
        return cur.lastrowid
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -k "insert" -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/db/store.py tests/test_db_store.py
git commit -m "feat: add OverrideStore.insert_override with validation"
```

---

## Task 4: `approve_override` + `reject_override`

**Files:**
- Modify: `src/db/store.py`
- Modify: `tests/test_db_store.py`

- [ ] **Step 1: Add the two approval tests to `tests/test_db_store.py`**

Append to the end of the file:

```python
def test_approve_override(store):
    row_id = _insert(store)
    store.approve_override(row_id, "buyer1")
    row = store._conn.execute(
        "SELECT * FROM analyst_overrides WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["approval_status"] == "approved"
    assert row["approved_by"] == "buyer1"
    assert row["approved_at"] is not None
    assert row["auto_approved"] == 0


def test_reject_override(store):
    row_id = _insert(store)
    store.reject_override(row_id, "buyer1", reason="Incorrect escalation — vendor fill rate is healthy")
    row = store._conn.execute(
        "SELECT * FROM analyst_overrides WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["approval_status"] == "rejected"
    assert row["rejected_by"] == "buyer1"
    assert row["rejected_at"] is not None
    assert row["rejection_reason"] == "Incorrect escalation — vendor fill rate is healthy"
    # Row must not be deleted
    count = store._conn.execute("SELECT COUNT(*) FROM analyst_overrides").fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -k "approve or reject" -v
```

Expected: `AttributeError: 'OverrideStore' object has no attribute 'approve_override'`

- [ ] **Step 3: Add both methods to `src/db/store.py`**

Add after `insert_override`:

```python
    def approve_override(self, override_id: int, approved_by: str) -> None:
        self._conn.execute(
            """
            UPDATE analyst_overrides
            SET approval_status = 'approved',
                approved_by     = ?,
                approved_at     = ?
            WHERE id = ? AND approval_status = 'pending'
            """,
            (approved_by, datetime.now(timezone.utc).isoformat(), override_id),
        )
        self._conn.commit()

    def reject_override(
        self, override_id: int, rejected_by: str, reason: Optional[str] = None
    ) -> None:
        self._conn.execute(
            """
            UPDATE analyst_overrides
            SET approval_status  = 'rejected',
                rejected_by      = ?,
                rejected_at      = ?,
                rejection_reason = ?
            WHERE id = ? AND approval_status = 'pending'
            """,
            (rejected_by, datetime.now(timezone.utc).isoformat(), reason, override_id),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -k "approve or reject" -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/db/store.py tests/test_db_store.py
git commit -m "feat: add OverrideStore.approve_override and reject_override"
```

---

## Task 5: `auto_approve_pending`

**Files:**
- Modify: `src/db/store.py`
- Modify: `tests/test_db_store.py`

- [ ] **Step 1: Add the `auto_approve_pending` test to `tests/test_db_store.py`**

Append to the end of the file:

```python
def test_auto_approve_pending(store):
    # Insert an old override (2 days ago) and a fresh one
    old_id = _insert(store, exception_id="EXC-OLD")
    new_id = _insert(store, exception_id="EXC-NEW")
    old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    store._conn.execute(
        "UPDATE analyst_overrides SET submitted_at = ? WHERE id = ?", (old_ts, old_id)
    )
    store._conn.commit()

    count = store.auto_approve_pending()

    assert count == 1
    old_row = store._conn.execute(
        "SELECT * FROM analyst_overrides WHERE id = ?", (old_id,)
    ).fetchone()
    new_row = store._conn.execute(
        "SELECT * FROM analyst_overrides WHERE id = ?", (new_id,)
    ).fetchone()
    assert old_row["approval_status"] == "approved"
    assert old_row["approved_by"] == "auto"
    assert old_row["auto_approved"] == 1
    assert new_row["approval_status"] == "pending"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_db_store.py::test_auto_approve_pending -v
```

Expected: `AttributeError: 'OverrideStore' object has no attribute 'auto_approve_pending'`

- [ ] **Step 3: Add `auto_approve_pending` to `src/db/store.py`**

Add after `reject_override`:

```python
    def auto_approve_pending(self) -> int:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=1)).isoformat()
        cur = self._conn.execute(
            """
            UPDATE analyst_overrides
            SET approval_status = 'approved',
                approved_by     = 'auto',
                approved_at     = ?,
                auto_approved   = 1
            WHERE approval_status = 'pending'
              AND submitted_at   <= ?
            """,
            (now.isoformat(), cutoff),
        )
        self._conn.commit()
        return cur.rowcount
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_db_store.py::test_auto_approve_pending -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/db/store.py tests/test_db_store.py
git commit -m "feat: add OverrideStore.auto_approve_pending with 1-day TTL"
```

---

## Task 6: `get_approved_few_shot_examples`

**Files:**
- Modify: `src/db/store.py`
- Modify: `tests/test_db_store.py`

- [ ] **Step 1: Add the five few-shot tests to `tests/test_db_store.py`**

Append to the end of the file:

```python
def test_get_approved_few_shot_examples_empty(store):
    assert store.get_approved_few_shot_examples() == []


def test_get_approved_few_shot_examples(store):
    row_id = _insert(store, override_compounding_risks=["promo_overlap"])
    store.approve_override(row_id, "buyer1")

    examples = store.get_approved_few_shot_examples()

    assert len(examples) == 1
    ex = examples[0]
    assert "input" in ex and "output" in ex
    assert ex["output"]["priority"] == "CRITICAL"
    assert ex["output"]["compounding_risks"] == ["promo_overlap"]
    assert ex["input"]["item_id"] == "ITM-001"


def test_get_approved_few_shot_examples_stratified(store):
    priorities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    for priority in priorities:
        for i in range(5):
            row_id = _insert(
                store,
                exception_id=f"EXC-{priority}-{i}",
                override_priority=priority,
            )
            store.approve_override(row_id, "buyer1")

    limit = 8
    examples = store.get_approved_few_shot_examples(limit=limit)

    assert len(examples) <= limit
    per_bucket = ceil(limit / 4)
    for priority in priorities:
        count = sum(1 for e in examples if e["output"].get("priority") == priority)
        assert count <= per_bucket, f"{priority} bucket exceeded cap: {count} > {per_bucket}"


def test_get_approved_few_shot_examples_90day_cutoff(store):
    row_id = _insert(store)
    store.approve_override(row_id, "buyer1")
    old_ts = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    store._conn.execute(
        "UPDATE analyst_overrides SET submitted_at = ? WHERE id = ?", (old_ts, row_id)
    )
    store._conn.commit()

    assert store.get_approved_few_shot_examples() == []


def test_duplicate_exception_id_allowed(store):
    id1 = _insert(store, override_priority="HIGH")
    id2 = _insert(store, override_priority="CRITICAL")
    assert id1 != id2
    count = store._conn.execute(
        "SELECT COUNT(*) FROM analyst_overrides WHERE exception_id = 'EXC-001'"
    ).fetchone()[0]
    assert count == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -k "few_shot or duplicate" -v
```

Expected: `AttributeError: 'OverrideStore' object has no attribute 'get_approved_few_shot_examples'`

- [ ] **Step 3: Add `get_approved_few_shot_examples` and `_row_to_few_shot` to `src/db/store.py`**

Add after `auto_approve_pending`:

```python
    def get_approved_few_shot_examples(self, limit: int = 10) -> list:
        cutoff_90d = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        per_bucket = ceil(limit / 4)
        priorities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

        rows: list[sqlite3.Row] = []
        seen_ids: set[int] = set()
        for priority in priorities:
            cur = self._conn.execute(
                """
                SELECT * FROM analyst_overrides
                WHERE approval_status = 'approved'
                  AND submitted_at   >= ?
                  AND override_priority = ?
                ORDER BY submitted_at DESC
                LIMIT ?
                """,
                (cutoff_90d, priority, per_bucket),
            )
            for row in cur.fetchall():
                if row["id"] not in seen_ids:
                    rows.append(row)
                    seen_ids.add(row["id"])

        # Fill remaining slots from non-priority-bucketed rows (e.g. analyst_note only)
        remaining = limit - len(rows)
        if remaining > 0 and seen_ids:
            placeholders = ",".join("?" * len(seen_ids))
            cur = self._conn.execute(
                f"""
                SELECT * FROM analyst_overrides
                WHERE approval_status = 'approved'
                  AND submitted_at   >= ?
                  AND id NOT IN ({placeholders})
                ORDER BY submitted_at DESC
                LIMIT ?
                """,
                (cutoff_90d, *seen_ids, remaining),
            )
            rows.extend(cur.fetchall())
        elif remaining > 0:
            cur = self._conn.execute(
                """
                SELECT * FROM analyst_overrides
                WHERE approval_status = 'approved'
                  AND submitted_at   >= ?
                ORDER BY submitted_at DESC
                LIMIT ?
                """,
                (cutoff_90d, remaining),
            )
            rows.extend(cur.fetchall())

        return [self._row_to_few_shot(r) for r in rows[:limit]]

    def _row_to_few_shot(self, row: sqlite3.Row) -> dict:
        output: dict = {}
        field_map = {
            "priority": "override_priority",
            "root_cause": "override_root_cause",
            "recommended_action": "override_recommended_action",
            "financial_impact_statement": "override_financial_impact_statement",
            "planner_brief": "override_planner_brief",
            "compounding_risks": "override_compounding_risks",
        }
        for out_key, col in field_map.items():
            val = row[col]
            if val is not None:
                output[out_key] = json.loads(val) if col == "override_compounding_risks" else val
        return {
            "input": json.loads(row["enriched_input_snapshot"]),
            "output": output,
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -k "few_shot or duplicate" -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/db/store.py tests/test_db_store.py
git commit -m "feat: add OverrideStore.get_approved_few_shot_examples with stratification and 90-day cutoff"
```

---

## Task 7: Full Suite Verification

**Files:**
- No new changes

- [ ] **Step 1: Run the complete `test_db_store.py` suite**

```bash
.venv/bin/python -m pytest tests/test_db_store.py -v
```

Expected: `12 passed` — all tests green:
```
test_init_creates_table               PASSED
test_init_enables_wal                 PASSED
test_insert_override                  PASSED
test_insert_override_no_fields_raises PASSED
test_insert_override_invalid_run_date PASSED
test_insert_override_analyst_note_only PASSED
test_approve_override                 PASSED
test_reject_override                  PASSED
test_auto_approve_pending             PASSED
test_get_approved_few_shot_examples_empty    PASSED
test_get_approved_few_shot_examples          PASSED
test_get_approved_few_shot_examples_stratified PASSED
test_get_approved_few_shot_examples_90day_cutoff PASSED
test_duplicate_exception_id_allowed   PASSED
```

Wait — the plan has 14 tests total. Expected count: `14 passed`.

- [ ] **Step 2: Run the full project test suite to verify no regressions**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all pre-existing 318 tests plus the 14 new ones = `332 passed`

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete analyst override DB layer — src/db/ + 14 tests passing"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 6 `OverrideStore` methods implemented (init, insert, approve, reject, auto_approve, get_few_shot). All 12 tests from spec table covered (14 in plan — 2 extra: `test_init_enables_wal`, `test_get_approved_few_shot_examples`). Schema DDL matches spec exactly including `CHECK` constraint and `rejection_reason`.
- [x] **No placeholders:** All steps have complete code blocks. No TBD/TODO.
- [x] **Type consistency:** `_insert` helper used across all tests. `OverrideStore` method signatures consistent across Tasks 3–6. `_row_to_few_shot` defined in Task 6 and used only there.
- [x] **`.gitignore`:** `output/overrides.db` added in Task 1.
- [x] **`data/schema/` mirror:** Created in Task 1.
- [x] **Parent dir creation:** `Path(db_path).parent.mkdir(parents=True, exist_ok=True)` in `__init__`, skipped for `:memory:`.
- [x] **`model_dump(mode='json')` note:** Spec calls for this at insert time; tests use a pre-serialized `SAMPLE_SNAPSHOT` dict, which is correct since callers (API layer) will serialize before calling `insert_override`.
