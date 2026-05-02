"""SQLite-backed store for downstream actions (Phase 13 — Agentic Engagement)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

class ActionStore:
    """Thin sqlite3 wrapper for the action_records table."""

    _SCHEMA_PATH = Path(__file__).parent / "schema.sql"

    def __init__(self, db_path: str = "output/actions.db") -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self._SCHEMA_PATH.read_text())
        self._conn.commit()

    def insert_action(
        self,
        request_id: str,
        exception_id: str,
        run_date: str,
        action_type: str,
        requested_by: str,
        requested_by_role: str,
        payload: dict,
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    request_id, exception_id, run_date, action_type,
                    requested_by, requested_by_role, json.dumps(payload),
                    now, now
                )
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            # Idempotency: request_id already exists. Just return the existing record.
            pass
            
        res = self.get_action(request_id)
        if not res:
            raise RuntimeError("Failed to retrieve action record after insert.")
        return res

    def get_action(self, request_id: str) -> Optional[dict]:
        cur = self._conn.execute("SELECT * FROM action_records WHERE request_id = ?", (request_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def get_actions_for_exception(self, exception_id: str) -> List[dict]:
        cur = self._conn.execute(
            "SELECT * FROM action_records WHERE exception_id = ? ORDER BY created_at DESC", 
            (exception_id,)
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def get_all_actions(
        self, 
        limit: int = 50, 
        offset: int = 0, 
        status: Optional[str] = None, 
        action_type: Optional[str] = None,
        run_date: Optional[str] = None
    ) -> dict:
        query = "SELECT * FROM action_records"
        count_query = "SELECT COUNT(*) FROM action_records"
        params = []
        conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if run_date:
            conditions.append("run_date = ?")
            params.append(run_date)

        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            query += where_clause
            count_query += where_clause

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        
        count_cur = self._conn.execute(count_query, params)
        total_count = count_cur.fetchone()[0]
        
        params.extend([limit, offset])
        cur = self._conn.execute(query, params)
        items = [self._row_to_dict(r) for r in cur.fetchall()]

        return {
            "items": items,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }

    def update_action_status(
        self, 
        request_id: str, 
        status: str, 
        failure_reason: Optional[str] = None,
        downstream_response: Optional[dict] = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resp_json = json.dumps(downstream_response) if downstream_response is not None else None
        
        self._conn.execute(
            """
            UPDATE action_records
            SET status = ?,
                updated_at = ?,
                failure_reason = ?,
                downstream_response = ?
            WHERE request_id = ?
            """,
            (status, now, failure_reason, resp_json, request_id)
        )
        self._conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["payload"] = json.loads(d["payload"]) if d.get("payload") else {}
        d["downstream_response"] = json.loads(d["downstream_response"]) if d.get("downstream_response") else None
        return d
