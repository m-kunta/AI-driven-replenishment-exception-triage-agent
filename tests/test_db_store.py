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
    # In-memory DBs use 'memory' mode; file-based DBs get 'wal'
    assert mode in ("wal", "memory")


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


def test_get_approved_few_shot_examples_note_only_fill_path(store):
    row_id = store.insert_override(
        exception_id="EXC-NOTE",
        run_date="2026-04-19",
        analyst_username="analyst1",
        enriched_input_snapshot=SAMPLE_SNAPSHOT,
        analyst_note="Phantom inventory — no field corrections needed.",
    )
    store.approve_override(row_id, "buyer1")

    examples = store.get_approved_few_shot_examples()

    assert len(examples) == 1
    ex = examples[0]
    assert ex["output"].get("analyst_note") == "Phantom inventory — no field corrections needed."
    assert "priority" not in ex["output"]


def test_duplicate_exception_id_allowed(store):
    id1 = _insert(store, override_priority="HIGH")
    id2 = _insert(store, override_priority="CRITICAL")
    assert id1 != id2
    count = store._conn.execute(
        "SELECT COUNT(*) FROM analyst_overrides WHERE exception_id = 'EXC-001'"
    ).fetchone()[0]
    assert count == 2
