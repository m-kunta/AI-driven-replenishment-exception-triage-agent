"""Tests for ExceptionLogger (Task 6.4)."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)
from src.output.exception_logger import ExceptionLogger, _FIELDNAMES, _LOG_FILENAME
from src.utils.config_loader import AppConfig, OutputConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.output = OutputConfig(log_dir=str(tmp_path))
    return cfg


def _make_triage_result(
    exception_id: str = "EXC-001",
    priority: Priority = Priority.CRITICAL,
    pattern_id: str | None = None,
    escalated_from: str | None = None,
    phantom_flag: bool = False,
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Vendor shipment delayed by 3 days",
        recommended_action="Expedite PO from secondary vendor",
        financial_impact_statement="$1,200 in lost weekly sales",
        planner_brief="Item at Tier 1 store with active promo. OOS imminent.",
        item_id="ITM-001",
        item_name="Premium Coffee Pods 48ct",
        store_id="STR-001",
        store_name="Downtown Flagship",
        exception_type="OOS",
        days_of_supply=0.5,
        store_tier=1,
        promo_active=True,
        est_lost_sales_value=1200.0,
        promo_margin_at_risk=300.0,
        dc_inventory_days=5.0,
        vendor_fill_rate_90d=0.87,
        pattern_id=pattern_id,
        escalated_from=escalated_from,
        phantom_flag=phantom_flag,
    )


def _make_run_result(results: list[TriageResult], run_id: str = "RUN-TESTABCD") -> TriageRunResult:
    return TriageRunResult(
        run_id=run_id,
        run_date=date(2026, 4, 11),
        triage_results=results,
        pattern_report=MacroPatternReport(),
        statistics=RunStatistics(total_exceptions=len(results)),
        run_timestamp=datetime(2026, 4, 11, 19, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExceptionLoggerInit:
    def test_log_path_derived_from_config(self, tmp_path):
        cfg = _make_config(tmp_path)
        logger = ExceptionLogger(cfg)
        assert logger._log_path == tmp_path / _LOG_FILENAME


class TestFirstWrite:
    def test_creates_file_with_header_on_first_log(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)
        run = _make_run_result([_make_triage_result()])

        path = el.log(run)

        assert path.exists()
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == _FIELDNAMES
            rows = list(reader)

        assert len(rows) == 1

    def test_correct_field_values_written(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)
        result = _make_triage_result(exception_id="EXC-999")
        run = _make_run_result([result], run_id="RUN-AABBCCDD")

        el.log(run)

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "RUN-AABBCCDD"
        assert row["exception_id"] == "EXC-999"
        assert row["item_id"] == "ITM-001"
        assert row["store_id"] == "STR-001"
        assert row["ai_priority"] == "CRITICAL"
        assert row["enrichment_confidence"] == "HIGH"
        assert row["missing_data_count"] == "0"
        assert row["phantom_flag"] == "False"
        assert row["ai_root_cause"] == "Vendor shipment delayed by 3 days"
        assert row["est_lost_sales_value"] == "1200.0000"

    def test_creates_parent_directory_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "logs"
        cfg = _make_config(nested)
        el = ExceptionLogger(cfg)
        run = _make_run_result([_make_triage_result()])

        path = el.log(run)
        assert path.exists()

    def test_none_fields_written_as_empty_string(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)
        result = _make_triage_result()
        # pattern_id and escalated_from default to None
        run = _make_run_result([result])
        el.log(run)

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["pattern_id"] == ""
        assert rows[0]["escalated_from"] == ""


class TestIdempotency:
    def test_relogging_same_run_does_not_duplicate_rows(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)
        run = _make_run_result([_make_triage_result()])

        el.log(run)
        el.log(run)  # second call should be a no-op

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 1

    def test_second_run_appends_without_duplicate_header(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)

        run1 = _make_run_result([_make_triage_result("EXC-001")], run_id="RUN-00000001")
        run2 = _make_run_result([_make_triage_result("EXC-002")], run_id="RUN-00000002")

        el.log(run1)
        el.log(run2)

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            content = f.read()

        # Only one header line
        assert content.count("run_id") == 1

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2
        run_ids = {r["run_id"] for r in rows}
        assert run_ids == {"RUN-00000001", "RUN-00000002"}

    def test_same_exception_id_different_run_id_both_written(self, tmp_path):
        """Same exception surfacing in two separate runs should produce two rows."""
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)

        run1 = _make_run_result([_make_triage_result("EXC-001")], run_id="RUN-AAAAAAAA")
        run2 = _make_run_result([_make_triage_result("EXC-001")], run_id="RUN-BBBBBBBB")

        el.log(run1)
        el.log(run2)

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 2


class TestMultipleResults:
    def test_all_results_in_run_written(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)

        results = [
            _make_triage_result(f"EXC-{i:03d}", priority=Priority.HIGH)
            for i in range(5)
        ]
        run = _make_run_result(results)
        el.log(run)

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 5

    def test_pattern_id_and_phantom_flag_written_correctly(self, tmp_path):
        cfg = _make_config(tmp_path)
        el = ExceptionLogger(cfg)

        result = _make_triage_result(
            pattern_id="PAT-VND-001",
            escalated_from="MEDIUM",
            phantom_flag=True,
        )
        run = _make_run_result([result])
        el.log(run)

        with open(tmp_path / _LOG_FILENAME, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        row = rows[0]
        assert row["pattern_id"] == "PAT-VND-001"
        assert row["escalated_from"] == "MEDIUM"
        assert row["phantom_flag"] == "True"
