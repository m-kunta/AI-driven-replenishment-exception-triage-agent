"""Tests for the TriageAgent orchestrator (Task 5.4).

All external dependencies (BatchProcessor, PatternAnalyzer, phantom webhook)
are mocked so no live LLM calls or HTTP requests are made.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.agent.batch_processor import BatchProcessorResult
from src.agent.triage_agent import TriageAgent
from src.models import (
    EnrichedExceptionSchema,
    EnrichmentConfidence,
    ExceptionType,
    MacroPatternReport,
    PatternDetail,
    PatternType,
    Priority,
    TriageResult,
    TriageRunResult,
)
from src.utils.config_loader import AppConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> AppConfig:
    return AppConfig()


def _make_enriched_exception(exception_id: str = "exc-001") -> EnrichedExceptionSchema:
    return EnrichedExceptionSchema(
        exception_id=exception_id,
        item_id="itm-001",
        item_name="Test Item",
        store_id="str-001",
        store_name="Test Store",
        exception_type=ExceptionType.OOS,
        exception_date=date(2026, 4, 1),
        units_on_hand=0,
        days_of_supply=0.0,
        source_system="TEST",
        batch_id="batch-001",
        ingested_at=datetime(2026, 4, 1, 8, 0, 0),
    )


def _make_triage_result(
    exception_id: str = "exc-001",
    priority: Priority = Priority.HIGH,
    compounding_risks: List[str] | None = None,
    phantom_flag: bool = False,
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Test root cause",
        recommended_action="Test action",
        financial_impact_statement="Test financial impact",
        planner_brief="Test brief",
        compounding_risks=compounding_risks or [],
        phantom_flag=phantom_flag,
    )


def _make_batch_result(
    triage_results: List[TriageResult] | None = None,
    batches_completed: int = 1,
    batches_failed: int = 0,
    total_input_tokens: int = 500,
    total_output_tokens: int = 200,
) -> BatchProcessorResult:
    return BatchProcessorResult(
        triage_results=triage_results or [],
        raw_pattern_analyses=[],
        batches_completed=batches_completed,
        batches_failed=batches_failed,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
    )


def _make_pattern_report(
    patterns: List[PatternDetail] | None = None,
    total_escalations: int = 0,
) -> MacroPatternReport:
    patterns = patterns or []
    return MacroPatternReport(
        patterns=patterns,
        total_patterns=len(patterns),
        total_escalations=total_escalations,
    )


def _make_agent_with_mocks(
    batch_result: BatchProcessorResult | None = None,
    pattern_report: MacroPatternReport | None = None,
) -> tuple[TriageAgent, MagicMock, MagicMock]:
    """Return (agent, mock_batch_processor, mock_pattern_analyzer)."""
    config = _make_config()
    agent = TriageAgent(config)

    mock_bp = MagicMock()
    mock_bp.process.return_value = batch_result or _make_batch_result()
    agent._batch_processor = mock_bp

    mock_pa = MagicMock()
    mock_pa.analyze.return_value = pattern_report or _make_pattern_report()
    agent._pattern_analyzer = mock_pa

    return agent, mock_bp, mock_pa


# ---------------------------------------------------------------------------
# Basic return-type and shape tests
# ---------------------------------------------------------------------------

def test_run_returns_triage_run_result():
    agent, _, _ = _make_agent_with_mocks()
    result = agent.run([_make_enriched_exception()])
    assert isinstance(result, TriageRunResult)


def test_run_id_format():
    agent, _, _ = _make_agent_with_mocks()
    result = agent.run([_make_enriched_exception()])
    assert re.fullmatch(r"RUN-[A-Z0-9]{8}", result.run_id), (
        f"run_id '{result.run_id}' does not match expected format RUN-XXXXXXXX"
    )


def test_run_date_defaults_to_today():
    agent, _, _ = _make_agent_with_mocks()
    result = agent.run([_make_enriched_exception()])
    assert result.run_date == date.today()


def test_run_date_uses_explicit_requested_date():
    agent, _, _ = _make_agent_with_mocks()
    requested_date = date(2026, 4, 29)
    result = agent.run([_make_enriched_exception()], run_date=requested_date)
    assert result.run_date == requested_date


def test_run_timestamp_is_set():
    agent, _, _ = _make_agent_with_mocks()
    result = agent.run([_make_enriched_exception()])
    assert isinstance(result.run_timestamp, datetime)


# ---------------------------------------------------------------------------
# Priority count accuracy
# ---------------------------------------------------------------------------

def test_priority_counts_accurate():
    triage_results = [
        _make_triage_result("e1", Priority.CRITICAL),
        _make_triage_result("e2", Priority.CRITICAL),
        _make_triage_result("e3", Priority.HIGH),
        _make_triage_result("e4", Priority.MEDIUM),
        _make_triage_result("e5", Priority.LOW),
        _make_triage_result("e6", Priority.LOW),
    ]
    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, _ = _make_agent_with_mocks(batch_result=batch_result)

    result = agent.run([_make_enriched_exception(f"e{i}") for i in range(1, 7)])

    assert result.statistics.critical_count == 2
    assert result.statistics.high_count == 1
    assert result.statistics.medium_count == 1
    assert result.statistics.low_count == 2
    assert result.statistics.total_exceptions == 6


# ---------------------------------------------------------------------------
# Phantom webhook tests
# ---------------------------------------------------------------------------

@patch("src.agent.triage_agent.process_phantom_inventory")
def test_phantom_webhook_fires_for_flagged(mock_webhook):
    triage_results = [
        _make_triage_result("e1", compounding_risks=["POTENTIAL_PHANTOM_INVENTORY"]),
        _make_triage_result("e2", compounding_risks=["POTENTIAL_PHANTOM_INVENTORY"]),
        _make_triage_result("e3", compounding_risks=[]),
    ]
    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, _ = _make_agent_with_mocks(batch_result=batch_result)

    agent.run([_make_enriched_exception(f"e{i}") for i in range(1, 4)])

    assert mock_webhook.call_count == 2
    called_ids = {call.args[0].exception_id for call in mock_webhook.call_args_list}
    assert called_ids == {"e1", "e2"}


@patch("src.agent.triage_agent.process_phantom_inventory")
def test_phantom_webhook_skips_unflagged(mock_webhook):
    triage_results = [
        _make_triage_result("e1", compounding_risks=["VENDOR_RELIABILITY"]),
        _make_triage_result("e2", compounding_risks=[]),
    ]
    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, _ = _make_agent_with_mocks(batch_result=batch_result)

    agent.run([_make_enriched_exception(f"e{i}") for i in range(1, 3)])

    mock_webhook.assert_not_called()


@patch("src.agent.triage_agent.process_phantom_inventory")
def test_phantom_flags_count_only_confirmed(mock_webhook):
    """phantom_flags counts results where phantom_flag=True after webhook, not all fired."""

    def _confirm_phantom(triage_result, config):
        # Confirm phantom only for e1, not e2
        if triage_result.exception_id == "e1":
            triage_result.phantom_flag = True

    mock_webhook.side_effect = _confirm_phantom

    triage_results = [
        _make_triage_result("e1", compounding_risks=["POTENTIAL_PHANTOM_INVENTORY"]),
        _make_triage_result("e2", compounding_risks=["POTENTIAL_PHANTOM_INVENTORY"]),
    ]
    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, _ = _make_agent_with_mocks(batch_result=batch_result)

    result = agent.run([_make_enriched_exception(f"e{i}") for i in range(1, 3)])

    assert mock_webhook.call_count == 2
    assert result.statistics.phantom_flags == 1  # only e1 confirmed


@patch("src.agent.triage_agent.process_phantom_inventory")
def test_phantom_webhook_receives_agent_config(mock_webhook):
    triage_results = [
        _make_triage_result("e1", compounding_risks=["POTENTIAL_PHANTOM_INVENTORY"])
    ]
    batch_result = _make_batch_result(triage_results=triage_results)
    config = _make_config()
    agent = TriageAgent(config)
    agent._batch_processor = MagicMock()
    agent._batch_processor.process.return_value = batch_result
    agent._pattern_analyzer = MagicMock()
    agent._pattern_analyzer.analyze.return_value = _make_pattern_report()

    agent.run([_make_enriched_exception("e1")])

    assert mock_webhook.call_args.args[1] is config.agent


# ---------------------------------------------------------------------------
# Pattern analysis tests
# ---------------------------------------------------------------------------

def test_pattern_report_in_result():
    pattern_report = _make_pattern_report(
        patterns=[
            PatternDetail(
                pattern_id="PAT-001",
                pattern_type=PatternType.VENDOR,
                group_key="VND-400",
                affected_count=5,
                description="Vendor fill rate drop",
            )
        ],
        total_escalations=3,
    )
    agent, _, _ = _make_agent_with_mocks(pattern_report=pattern_report)

    result = agent.run([_make_enriched_exception()])

    assert result.pattern_report is pattern_report
    assert result.pattern_report.total_patterns == 1
    assert result.pattern_report.total_escalations == 3


def test_escalations_count_from_pattern_report():
    pattern_report = _make_pattern_report(total_escalations=7)
    agent, _, _ = _make_agent_with_mocks(pattern_report=pattern_report)

    result = agent.run([_make_enriched_exception()])

    assert result.statistics.pattern_escalations == 7


def test_pattern_analyzer_receives_triage_results_and_enriched():
    triage_results = [_make_triage_result("e1")]
    enriched = [_make_enriched_exception("e1")]
    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, mock_pa = _make_agent_with_mocks(batch_result=batch_result)

    agent.run(enriched)

    mock_pa.analyze.assert_called_once()
    call_args = mock_pa.analyze.call_args
    assert call_args.args[0] == triage_results
    assert call_args.args[1] == enriched


def test_pattern_escalations_reflected_in_results():
    """Verify that PatternAnalyzer mutations to triage_results are included in output."""
    triage_results = [
        _make_triage_result("e1", Priority.MEDIUM),
        _make_triage_result("e2", Priority.MEDIUM),
    ]

    def _escalate(results, enriched):
        for r in results:
            r.priority = Priority.HIGH
            r.escalated_from = "MEDIUM"
            r.pattern_id = "PAT-001"
        return _make_pattern_report(total_escalations=2)

    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, mock_pa = _make_agent_with_mocks(batch_result=batch_result)
    mock_pa.analyze.side_effect = _escalate

    result = agent.run([_make_enriched_exception(f"e{i}") for i in range(1, 3)])

    assert result.statistics.high_count == 2
    assert result.statistics.medium_count == 0
    assert all(r.escalated_from == "MEDIUM" for r in result.triage_results)
    assert all(r.pattern_id == "PAT-001" for r in result.triage_results)


# ---------------------------------------------------------------------------
# Batch stats propagation
# ---------------------------------------------------------------------------

def test_batch_stats_propagated():
    batch_result = _make_batch_result(
        triage_results=[_make_triage_result()],
        batches_completed=4,
        batches_failed=1,
        total_input_tokens=1200,
        total_output_tokens=480,
    )
    agent, _, _ = _make_agent_with_mocks(batch_result=batch_result)

    result = agent.run([_make_enriched_exception()])

    stats = result.statistics
    assert stats.batches_completed == 4
    assert stats.batches_failed == 1
    assert stats.total_input_tokens == 1200
    assert stats.total_output_tokens == 480


def test_triage_results_passed_through():
    triage_results = [_make_triage_result(f"e{i}") for i in range(5)]
    batch_result = _make_batch_result(triage_results=triage_results)
    agent, _, _ = _make_agent_with_mocks(batch_result=batch_result)

    result = agent.run([_make_enriched_exception(f"e{i}") for i in range(5)])

    assert result.triage_results == triage_results


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@patch("src.agent.triage_agent.process_phantom_inventory")
def test_empty_input(mock_webhook):
    agent, _, _ = _make_agent_with_mocks(batch_result=_make_batch_result(triage_results=[]))

    result = agent.run([])

    assert isinstance(result, TriageRunResult)
    assert result.statistics.total_exceptions == 0
    assert result.statistics.critical_count == 0
    assert result.statistics.high_count == 0
    assert result.statistics.medium_count == 0
    assert result.statistics.low_count == 0
    assert result.statistics.phantom_flags == 0
    mock_webhook.assert_not_called()


def test_pipeline_duration_is_non_negative():
    agent, _, _ = _make_agent_with_mocks()
    result = agent.run([_make_enriched_exception()])
    assert result.statistics.pipeline_duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# Full orchestration smoke test (120 mock records)
# ---------------------------------------------------------------------------

@patch("src.agent.triage_agent.process_phantom_inventory")
def test_full_run_120_records(mock_webhook):
    """Full orchestration with 120 mock enriched exceptions completes without error."""
    priorities = [Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW]
    triage_results = [
        _make_triage_result(f"exc-{i:03d}", priorities[i % 4])
        for i in range(120)
    ]
    # Add 10 phantom-flagged exceptions
    for r in triage_results[:10]:
        r.compounding_risks = ["POTENTIAL_PHANTOM_INVENTORY"]

    # Simulate 3 phantom confirmations
    confirmed = set()

    def _confirm_some(result, config):
        if result.exception_id in {"exc-000", "exc-004", "exc-008"}:
            result.phantom_flag = True
            confirmed.add(result.exception_id)

    mock_webhook.side_effect = _confirm_some

    batch_result = _make_batch_result(
        triage_results=triage_results,
        batches_completed=4,
        batches_failed=0,
        total_input_tokens=12000,
        total_output_tokens=4800,
    )
    pattern_report = _make_pattern_report(
        patterns=[
            PatternDetail(
                pattern_id="PAT-VND-001",
                pattern_type=PatternType.VENDOR,
                group_key="VND-400",
                affected_count=14,
                description="CleanHome fill rate collapse",
                escalation_count=5,
            )
        ],
        total_escalations=5,
    )
    agent, _, _ = _make_agent_with_mocks(
        batch_result=batch_result,
        pattern_report=pattern_report,
    )

    result = agent.run([_make_enriched_exception(f"exc-{i:03d}") for i in range(120)])

    assert isinstance(result, TriageRunResult)
    assert result.statistics.total_exceptions == 120
    assert result.statistics.critical_count == 30   # indices 0,4,8,...
    assert result.statistics.high_count == 30
    assert result.statistics.medium_count == 30
    assert result.statistics.low_count == 30
    assert result.statistics.phantom_flags == 3
    assert result.statistics.pattern_escalations == 5
    assert result.statistics.batches_completed == 4
    assert result.statistics.total_input_tokens == 12000
    assert mock_webhook.call_count == 10
    assert re.fullmatch(r"RUN-[A-Z0-9]{8}", result.run_id)
