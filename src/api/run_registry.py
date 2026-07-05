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
