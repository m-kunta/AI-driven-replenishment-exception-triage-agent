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

    def get_approved_few_shot_examples(self, limit: int = 10) -> list:
        cutoff_90d = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        per_bucket = ceil(limit / 4)
        priorities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

        rows: list = []
        seen_ids: set = set()
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

    def _row_to_few_shot(self, row) -> dict:
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
        if row["analyst_note"] is not None:
            output["analyst_note"] = row["analyst_note"]
        return {
            "input": json.loads(row["enriched_input_snapshot"]),
            "output": output,
        }
