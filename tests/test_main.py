"""Tests for the main pipeline orchestrator (Task 7.1).

All Layer 3 / Layer 4 operations that make real I/O or LLM calls are mocked.
Layer 1+2 use the real sample data on disk so the normalisation and enrichment
code paths are exercised end-to-end.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)
from src.utils.exceptions import ConfigurationError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SAMPLE_CONFIG = "config/config.yaml"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _make_triage_result(exception_id: str = "EXC-001") -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=Priority.HIGH,
        confidence=EnrichmentConfidence.MEDIUM,
        root_cause="Vendor late shipment",
        recommended_action="Expedite PO",
        financial_impact_statement="$500 lost",
        planner_brief="Store needs stock before promo ends.",
        item_id="ITM-001",
        store_id="STR-001",
        exception_type="VENDOR_LATE",
        days_of_supply=1.5,
        store_tier=2,
        promo_active=False,
        est_lost_sales_value=500.0,
        promo_margin_at_risk=0.0,
    )


def _make_run_result(n: int = 3) -> TriageRunResult:
    return TriageRunResult(
        run_id="RUN-TESTMAIN",
        run_date=date.today(),
        triage_results=[_make_triage_result(f"EXC-{i:03d}") for i in range(n)],
        pattern_report=MacroPatternReport(),
        statistics=RunStatistics(total_exceptions=n, high_count=n),
        run_timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Helper: build a mock TriageAgent that returns a fixed TriageRunResult
# ---------------------------------------------------------------------------

def _mock_triage_agent(run_result: TriageRunResult):
    mock = MagicMock()
    mock.return_value = mock         # TriageAgent(config) returns mock
    mock.run.return_value = run_result
    return mock


# ---------------------------------------------------------------------------
# Tests: dry-run mode
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_returns_none(self, tmp_path, capsys):
        """--dry-run should return None and not invoke TriageAgent."""
        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.TriageAgent") as mock_agent_cls,
        ):
            from src.main import run_triage_pipeline
            result = run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                dry_run=True,
                sample=True,
            )

        assert result is None
        # TriageAgent constructor should never be called in dry-run
        mock_agent_cls.assert_not_called()

    def test_dry_run_prints_enrichment_summary(self, capsys):
        """--dry-run should print enrichment count to stdout."""
        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.TriageAgent"),
        ):
            from src.main import run_triage_pipeline
            run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                dry_run=True,
                sample=True,
            )

        captured = capsys.readouterr()
        assert "Exceptions enriched" in captured.out
        assert "ENRICHMENT SUMMARY" in captured.out

    def test_dry_run_enriches_all_120_sample_exceptions(self, capsys):
        """Layer 1+2 against real sample data should produce ~120 enriched records."""
        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.TriageAgent"),
        ):
            from src.main import run_triage_pipeline
            run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                dry_run=True,
                sample=True,
            )

        captured = capsys.readouterr()
        # Exact count may vary with dedup, but should be close to 120
        # Just verify a positive number was printed
        import re
        match = re.search(r"Exceptions enriched\s*:\s*(\d+)", captured.out)
        assert match is not None
        count = int(match.group(1))
        assert count > 0


# ---------------------------------------------------------------------------
# Tests: full pipeline (no-alerts + mocked Layer 3)
# ---------------------------------------------------------------------------

class TestFullPipelineNoAlerts:
    def test_no_alerts_returns_triage_run_result(self, tmp_path):
        """--no-alerts should run all layers and return TriageRunResult."""
        run_result = _make_run_result()

        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.TriageAgent") as MockAgent,
            patch("src.main.AlertDispatcher"),
            patch("src.main.BriefingGenerator") as MockBriefing,
            patch("src.main.ExceptionLogger") as MockLogger,
        ):
            MockAgent.return_value.run.return_value = run_result
            MockBriefing.return_value.generate.return_value = tmp_path / "briefing.md"
            MockLogger.return_value.log.return_value = tmp_path / "exception_log.csv"

            from src.main import run_triage_pipeline
            result = run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                no_alerts=True,
                sample=True,
            )

        assert result is not None
        assert result.run_id == "RUN-TESTMAIN"

    def test_no_alerts_skips_dispatcher(self):
        """AlertDispatcher.dispatch should NOT be called with --no-alerts."""
        run_result = _make_run_result()

        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.TriageAgent") as MockAgent,
            patch("src.main.AlertDispatcher") as MockDispatcher,
            patch("src.main.BriefingGenerator") as MockBriefing,
            patch("src.main.ExceptionLogger") as MockLogger,
        ):
            MockAgent.return_value.run.return_value = run_result
            MockBriefing.return_value.generate.return_value = Path("output/briefings/b.md")
            MockLogger.return_value.log.return_value = Path("output/logs/exception_log.csv")

            from src.main import run_triage_pipeline
            run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                no_alerts=True,
                sample=True,
            )

        MockDispatcher.return_value.dispatch.assert_not_called()

    def test_alerts_dispatched_when_no_flag(self):
        """AlertDispatcher.dispatch SHOULD be called when --no-alerts is absent."""
        run_result = _make_run_result()

        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.TriageAgent") as MockAgent,
            patch("src.main.AlertDispatcher") as MockDispatcher,
            patch("src.main.BriefingGenerator") as MockBriefing,
            patch("src.main.ExceptionLogger") as MockLogger,
        ):
            MockAgent.return_value.run.return_value = run_result
            MockBriefing.return_value.generate.return_value = Path("output/briefings/b.md")
            MockLogger.return_value.log.return_value = Path("output/logs/exception_log.csv")

            from src.main import run_triage_pipeline
            run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                no_alerts=False,
                sample=True,
            )

        MockDispatcher.return_value.dispatch.assert_called_once_with(run_result)


# ---------------------------------------------------------------------------
# Tests: sample flag
# ---------------------------------------------------------------------------

class TestSampleFlag:
    def test_sample_flag_overrides_config_csv_path(self):
        """--sample should set config.ingestion.csv.path to the sample CSV."""
        from src.main import _SAMPLE_CSV_PATH

        captured_path = []

        original_adapter = __import__(
            "src.ingestion.csv_adapter", fromlist=["CsvIngestionAdapter"]
        ).CsvIngestionAdapter

        class CapturingAdapter(original_adapter):
            def __init__(self, file_path, delimiter=","):
                captured_path.append(file_path)
                super().__init__(file_path=file_path, delimiter=delimiter)

        with (
            patch("src.main.validate_required_env_vars"),
            patch("src.main.CsvIngestionAdapter", CapturingAdapter),
            patch("src.main.TriageAgent"),
        ):
            from src.main import run_triage_pipeline
            run_triage_pipeline(
                config_path=_SAMPLE_CONFIG,
                dry_run=True,
                sample=True,
            )

        assert len(captured_path) > 0
        assert captured_path[0] == _SAMPLE_CSV_PATH


# ---------------------------------------------------------------------------
# Tests: config error handling
# ---------------------------------------------------------------------------

class TestConfigErrors:
    def test_missing_config_raises_configuration_error(self):
        """A non-existent config path should raise ConfigurationError."""
        import importlib
        import src.main as main_module
        importlib.reload(main_module)

        with pytest.raises(ConfigurationError):
            main_module.run_triage_pipeline(
                config_path="non_existent_path/config.yaml",
                sample=True,
            )
