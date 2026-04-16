"""Exception logger for Layer 4 audit trail (Task 6.4).

Appends one flat CSV row per TriageResult to output/logs/exception_log.csv.
The file is idempotent on (run_id, exception_id): re-logging the same run
never produces duplicate rows.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Set, Tuple

from src.models import TriageResult, TriageRunResult
from src.utils.config_loader import AppConfig

logger = logging.getLogger(__name__)

# Ordered list of CSV column names — matches the spec schema for Task 6.4.
_FIELDNAMES: list[str] = [
    "run_id",
    "run_date",
    "exception_id",
    "item_id",
    "store_id",
    "exception_type",
    "exception_date",
    "days_of_supply",
    "promo_active",
    "store_tier",
    "vendor_fill_rate_90d",
    "dc_inventory_days",
    "est_lost_sales_value",
    "promo_margin_at_risk",
    "enrichment_confidence",
    "missing_data_count",
    "ai_priority",
    "ai_confidence",
    "ai_root_cause",
    "ai_recommended_action",
    "ai_financial_impact",
    "ai_planner_brief",
    "pattern_id",
    "escalated_from",
    "phantom_flag",
    "run_timestamp",
]

_LOG_FILENAME = "exception_log.csv"


class ExceptionLogger:
    """Appends triage results to a persistent CSV audit log.

    Instantiate once with AppConfig, then call log() after every triage run.
    The log file is created (with header) on first write and appended
    thereafter. Idempotency is enforced: rows for a (run_id, exception_id)
    pair that already exist in the file are silently skipped.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._log_path = Path(config.output.log_dir) / _LOG_FILENAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, run_result: TriageRunResult) -> Path:
        """Append all triage results from run_result to the CSV log.

        Args:
            run_result: Completed triage run from the Layer 3 / Layer 4 pipeline.

        Returns:
            Path to the exception log file.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        existing_keys = self._read_existing_keys()
        new_rows = self._build_rows(run_result, existing_keys)

        if not new_rows:
            logger.info(
                "ExceptionLogger: all %d results already logged for run %s — skipping.",
                len(run_result.triage_results),
                run_result.run_id,
            )
            return self._log_path

        write_header = not self._log_path.exists() or self._log_path.stat().st_size == 0

        with open(self._log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerows(new_rows)

        logger.info(
            "ExceptionLogger: appended %d rows for run %s → %s",
            len(new_rows),
            run_result.run_id,
            self._log_path,
        )
        return self._log_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_existing_keys(self) -> Set[Tuple[str, str]]:
        """Return the set of (run_id, exception_id) pairs already in the log."""
        if not self._log_path.exists():
            return set()

        keys: Set[Tuple[str, str]] = set()
        try:
            with open(self._log_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    run_id = row.get("run_id", "")
                    exc_id = row.get("exception_id", "")
                    if run_id and exc_id:
                        keys.add((run_id, exc_id))
        except (OSError, csv.Error) as exc:
            logger.warning("ExceptionLogger: could not read existing log (%s); treating as empty.", exc)

        return keys

    def _build_rows(
        self,
        run_result: TriageRunResult,
        existing_keys: Set[Tuple[str, str]],
    ) -> list[dict]:
        """Convert TriageResults to flat CSV row dicts, skipping duplicates."""
        rows = []
        run_id = run_result.run_id
        run_date = str(run_result.run_date)
        run_timestamp = run_result.run_timestamp.isoformat()

        for result in run_result.triage_results:
            key = (run_id, result.exception_id)
            if key in existing_keys:
                logger.debug("ExceptionLogger: skipping duplicate row %s / %s", run_id, result.exception_id)
                continue

            rows.append(self._result_to_row(result, run_id, run_date, run_timestamp))

        return rows

    def _result_to_row(
        self,
        result: TriageResult,
        run_id: str,
        run_date: str,
        run_timestamp: str,
    ) -> dict:
        """Map a single TriageResult to a flat CSV row dict."""

        def _safe(value) -> str:
            """Coerce any value (including None) to a safe CSV string."""
            if value is None:
                return ""
            if isinstance(value, bool):
                return str(value)
            if isinstance(value, float):
                return f"{value:.4f}"
            return str(value)

        return {
            "run_id": run_id,
            "run_date": run_date,
            "exception_id": result.exception_id,
            "item_id": _safe(result.item_id),
            "store_id": _safe(result.store_id),
            "exception_type": _safe(result.exception_type),
            "exception_date": _safe(result.exception_date),
            "days_of_supply": _safe(result.days_of_supply),
            "promo_active": _safe(result.promo_active),
            "store_tier": _safe(result.store_tier),
            "vendor_fill_rate_90d": _safe(result.vendor_fill_rate_90d),
            "dc_inventory_days": _safe(result.dc_inventory_days),
            "est_lost_sales_value": _safe(result.est_lost_sales_value),
            "promo_margin_at_risk": _safe(result.promo_margin_at_risk),
            "enrichment_confidence": result.confidence.value,
            "missing_data_count": str(len(result.missing_data_flags)),
            "ai_priority": result.priority.value,
            "ai_confidence": result.confidence.value,
            "ai_root_cause": result.root_cause,
            "ai_recommended_action": result.recommended_action,
            "ai_financial_impact": result.financial_impact_statement,
            "ai_planner_brief": result.planner_brief,
            "pattern_id": _safe(result.pattern_id),
            "escalated_from": _safe(result.escalated_from),
            "phantom_flag": _safe(result.phantom_flag),
            "run_timestamp": run_timestamp,
        }
