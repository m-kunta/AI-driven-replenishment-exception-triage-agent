"""Tests for the BriefingGenerator (Task 6.3).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent.llm_provider import LLMResponse
from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    PatternDetail,
    PatternType,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)
from src.output.briefing_generator import BriefingGenerator
from src.utils.config_loader import AppConfig


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path) -> AppConfig:
    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "briefings")
    return config


def _make_result(
    exception_id: str = "exc-001",
    priority: Priority = Priority.HIGH,
    item_name: str = "Test Item",
    store_name: str = "Test Store",
    est_lost_sales_value: float = 500.0,
    days_of_supply: float = 2.0,
    store_tier: int = 2,
    root_cause: str = "Vendor delay",
    recommended_action: str = "Contact vendor",
    planner_brief: str = "Vendor has been late for three consecutive weeks.",
    compounding_risks: list | None = None,
    missing_data_flags: list | None = None,
    promo_margin_at_risk: float = 100.0,
    exception_type: str = "OOS",
    confidence: EnrichmentConfidence = EnrichmentConfidence.HIGH,
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=confidence,
        root_cause=root_cause,
        recommended_action=recommended_action,
        financial_impact_statement="High financial impact",
        planner_brief=planner_brief,
        item_name=item_name,
        store_name=store_name,
        store_tier=store_tier,
        est_lost_sales_value=est_lost_sales_value,
        days_of_supply=days_of_supply,
        exception_type=exception_type,
        promo_margin_at_risk=promo_margin_at_risk,
        compounding_risks=compounding_risks or [],
        missing_data_flags=missing_data_flags or [],
    )


def _make_run_result(
    results: list | None = None,
    patterns: list | None = None,
    total_escalations: int = 0,
    run_date: date | None = None,
) -> TriageRunResult:
    results = results or [
        _make_result("c1", Priority.CRITICAL, est_lost_sales_value=2000.0),
        _make_result("h1", Priority.HIGH, est_lost_sales_value=800.0),
        _make_result("m1", Priority.MEDIUM, est_lost_sales_value=300.0),
        _make_result("l1", Priority.LOW, est_lost_sales_value=50.0),
    ]
    pattern_report = MacroPatternReport(
        patterns=patterns or [],
        total_patterns=len(patterns or []),
        total_escalations=total_escalations,
    )
    counts = {p: sum(1 for r in results if r.priority == p) for p in Priority}
    stats = RunStatistics(
        total_exceptions=len(results),
        critical_count=counts[Priority.CRITICAL],
        high_count=counts[Priority.HIGH],
        medium_count=counts[Priority.MEDIUM],
        low_count=counts[Priority.LOW],
        batches_completed=2,
        batches_failed=0,
        pattern_escalations=total_escalations,
        phantom_flags=0,
        total_input_tokens=1000,
        total_output_tokens=400,
        pipeline_duration_seconds=4.5,
    )
    return TriageRunResult(
        run_id="RUN-ABCD1234",
        run_date=run_date or date(2026, 4, 10),
        triage_results=results,
        pattern_report=pattern_report,
        statistics=stats,
        run_timestamp=datetime(2026, 4, 10, 7, 0, 0, tzinfo=timezone.utc),
    )


def _mock_llm(text: str = "Today's supply chain situation is serious.") -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = LLMResponse(
        text=text, input_tokens=200, output_tokens=80
    )
    return provider


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_generate_returns_path(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    gen = BriefingGenerator(_make_config(tmp_path))
    result = gen.generate(_make_run_result())
    assert isinstance(result, Path)


@patch("src.output.briefing_generator.get_provider")
def test_briefing_file_written(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    gen = BriefingGenerator(_make_config(tmp_path))
    path = gen.generate(_make_run_result())
    assert path.exists()
    assert path.stat().st_size > 0


@patch("src.output.briefing_generator.get_provider")
def test_briefing_filename_contains_run_date(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    run_result = _make_run_result(run_date=date(2026, 4, 10))
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    assert "2026-04-10" in path.name


@patch("src.output.briefing_generator.get_provider")
def test_briefing_dir_created_if_missing(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "nested" / "briefings")
    gen = BriefingGenerator(config)
    path = gen.generate(_make_run_result())
    assert path.exists()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_header_contains_run_id(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    run_result = _make_run_result()
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    assert "RUN-ABCD1234" in content


@patch("src.output.briefing_generator.get_provider")
def test_header_contains_date(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    assert "2026-04-10" in path.read_text()


# ---------------------------------------------------------------------------
# At-a-Glance table — key acceptance criterion: totals must match sums
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_at_a_glance_counts_accurate(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    results = [
        _make_result("c1", Priority.CRITICAL),
        _make_result("c2", Priority.CRITICAL),
        _make_result("h1", Priority.HIGH),
        _make_result("m1", Priority.MEDIUM),
    ]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    assert "| 🔴 CRITICAL | 2 |" in content
    assert "| 🟠 HIGH | 1 |" in content
    assert "| 🟡 MEDIUM | 1 |" in content
    assert "| 🟢 LOW | 0 |" in content


@patch("src.output.briefing_generator.get_provider")
def test_financial_totals_match_sum(mock_gp, tmp_path):
    """Acceptance criterion: financial totals in table match sum of individual values."""
    mock_gp.return_value = _mock_llm()
    results = [
        _make_result("c1", Priority.CRITICAL, est_lost_sales_value=1500.0),
        _make_result("c2", Priority.CRITICAL, est_lost_sales_value=2500.0),  # CRITICAL total = 4000
        _make_result("h1", Priority.HIGH, est_lost_sales_value=800.0),
    ]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    assert "$4,000" in content  # CRITICAL total (1500 + 2500)
    assert "$800" in content    # HIGH total
    assert "$4,800" in content  # grand total (4000 + 800)


@patch("src.output.briefing_generator.get_provider")
def test_financial_totals_grand_total(mock_gp, tmp_path):
    """Grand total row matches exact sum of all est_lost_sales_value."""
    mock_gp.return_value = _mock_llm()
    results = [
        _make_result("c1", Priority.CRITICAL, est_lost_sales_value=1000.0),
        _make_result("h1", Priority.HIGH, est_lost_sales_value=500.0),
    ]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    # Grand total = 1500
    assert "$1,500" in content


# ---------------------------------------------------------------------------
# Executive summary — LLM is called exactly once
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_executive_summary_section_present(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm("Supply chain is under pressure.")
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    assert "## Executive Summary" in path.read_text()


@patch("src.output.briefing_generator.get_provider")
def test_executive_summary_uses_llm_text(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm("The highest risk today is Item-X at Store-Y.")
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    assert "The highest risk today is Item-X at Store-Y." in path.read_text()


@patch("src.output.briefing_generator.get_provider")
def test_llm_called_exactly_once(mock_gp, tmp_path):
    mock_provider = _mock_llm()
    mock_gp.return_value = mock_provider
    BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    assert mock_provider.complete.call_count == 1


@patch("src.output.briefing_generator.get_provider")
def test_llm_failure_falls_back_gracefully(mock_gp, tmp_path):
    """Briefing is still written when LLM call raises an exception."""
    mock_provider = MagicMock()
    mock_provider.complete.side_effect = RuntimeError("API key missing")
    mock_gp.return_value = mock_provider
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    assert path.exists()
    content = path.read_text()
    assert "## Executive Summary" in content
    assert "generation failed" in content.lower()


# ---------------------------------------------------------------------------
# Top Critical Exceptions — key acceptance criterion: all CRITICAL appear
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_all_critical_appear_in_top_section(mock_gp, tmp_path):
    """Acceptance criterion: all CRITICAL exceptions appear in the top section."""
    mock_gp.return_value = _mock_llm()
    results = [
        _make_result("c1", Priority.CRITICAL, item_name="ItemAlpha", store_name="StoreA"),
        _make_result("c2", Priority.CRITICAL, item_name="ItemBeta", store_name="StoreB"),
        _make_result("c3", Priority.CRITICAL, item_name="ItemGamma", store_name="StoreC"),
        _make_result("h1", Priority.HIGH, item_name="ItemDelta", store_name="StoreD"),
    ]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    assert "ItemAlpha" in content
    assert "ItemBeta" in content
    assert "ItemGamma" in content


@patch("src.output.briefing_generator.get_provider")
def test_critical_sorted_by_financial_exposure_desc(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    results = [
        _make_result("c1", Priority.CRITICAL, item_name="LowExposure", est_lost_sales_value=100.0),
        _make_result("c2", Priority.CRITICAL, item_name="HighExposure", est_lost_sales_value=9000.0),
    ]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    # HighExposure should appear before LowExposure in the top section
    assert content.index("HighExposure") < content.index("LowExposure")


@patch("src.output.briefing_generator.get_provider")
def test_no_critical_shows_placeholder(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    results = [_make_result("h1", Priority.HIGH)]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    assert "No CRITICAL exceptions" in path.read_text()


@patch("src.output.briefing_generator.get_provider")
def test_compounding_risks_shown_in_critical_card(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    results = [_make_result("c1", Priority.CRITICAL, compounding_risks=["VENDOR_RELIABILITY", "PROMO_COMMITMENT"])]
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result(results=results))
    assert "VENDOR_RELIABILITY" in path.read_text()


@patch("src.output.briefing_generator.get_provider")
def test_missing_data_shown_in_critical_card(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    results = [_make_result("c1", Priority.CRITICAL, missing_data_flags=["vendor_fill_rate_90d"])]
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result(results=results))
    assert "vendor_fill_rate_90d" in path.read_text()


# ---------------------------------------------------------------------------
# Systemic patterns section
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_patterns_section_present_when_patterns_exist(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    patterns = [
        PatternDetail(
            pattern_id="PAT-001",
            pattern_type=PatternType.VENDOR,
            group_key="VND-400",
            affected_count=7,
            description="Vendor fill rate collapsed",
            escalation_count=3,
        )
    ]
    run_result = _make_run_result(patterns=patterns, total_escalations=3)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    assert "VND-400" in content
    assert "Vendor fill rate collapsed" in content
    assert "3 escalations" in content


@patch("src.output.briefing_generator.get_provider")
def test_patterns_section_no_patterns(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    run_result = _make_run_result(patterns=[])
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    assert "No systemic patterns detected" in path.read_text()


# ---------------------------------------------------------------------------
# Full exception queue
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_full_queue_contains_all_exceptions(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    results = [
        _make_result(f"e{i}", Priority.HIGH, item_name=f"Item{i}") for i in range(5)
    ]
    run_result = _make_run_result(results=results)
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    for i in range(5):
        assert f"Item{i}" in content


@patch("src.output.briefing_generator.get_provider")
def test_full_queue_section_header_present(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    assert "## Full Exception Queue" in path.read_text()


# ---------------------------------------------------------------------------
# Run statistics section
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_run_statistics_section_present(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    path = BriefingGenerator(_make_config(tmp_path)).generate(_make_run_result())
    content = path.read_text()
    assert "## Run Statistics" in content
    assert "Total exceptions processed:" in content
    assert "Pipeline completion time:" in content


@patch("src.output.briefing_generator.get_provider")
def test_run_statistics_values_accurate(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    run_result = _make_run_result()  # 4 results, 2 batches, 4.5s
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    content = path.read_text()
    assert "Total exceptions processed: 4" in content
    assert "Batches: 2 completed, 0 failed" in content
    assert "4.5s" in content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@patch("src.output.briefing_generator.get_provider")
def test_empty_results_generates_valid_briefing(mock_gp, tmp_path):
    mock_gp.return_value = _mock_llm()
    run_result = _make_run_result(results=[])
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    assert path.exists()
    content = path.read_text()
    assert "## Today at a Glance" in content
    assert "## Executive Summary" in content


@patch("src.output.briefing_generator.get_provider")
def test_none_financial_values_treated_as_zero(mock_gp, tmp_path):
    """est_lost_sales_value=None should not raise and should render as $0."""
    mock_gp.return_value = _mock_llm()
    result = _make_result("c1", Priority.CRITICAL, est_lost_sales_value=0.0)
    result.est_lost_sales_value = None  # force None
    run_result = _make_run_result(results=[result])
    path = BriefingGenerator(_make_config(tmp_path)).generate(run_result)
    assert path.exists()  # no crash


@patch("src.output.briefing_generator.get_provider")
def test_generate_overwrites_existing_briefing(mock_gp, tmp_path):
    """Calling generate() twice on the same run_date overwrites the file."""
    mock_gp.return_value = _mock_llm("First run.")
    config = _make_config(tmp_path)
    gen = BriefingGenerator(config)
    run_result = _make_run_result()
    path1 = gen.generate(run_result)

    mock_gp.return_value = _mock_llm("Second run.")
    path2 = gen.generate(run_result)

    assert path1 == path2
    assert "Second run." in path2.read_text()
