"""Tests for the PatternAnalyzer (Task 5.2).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    EnrichedExceptionSchema,
    EnrichmentConfidence,
    ExceptionType,
    MacroPatternReport,
    PatternDetail,
    PatternType,
    Priority,
    TriageResult,
)
from src.utils.config_loader import AppConfig


def _make_enriched_exception(
    exception_id: str = "exc-001",
    vendor_id: str = "VND-001",
    region: str = "Northeast",
    category: str = "Dairy",
    store_id: str = "STR-001",
) -> EnrichedExceptionSchema:
    return EnrichedExceptionSchema(
        exception_id=exception_id,
        item_id="itm-001",
        item_name="Test Item",
        store_id=store_id,
        store_name="Test Store",
        exception_type=ExceptionType.OOS,
        exception_date=date(2026, 4, 1),
        units_on_hand=0,
        days_of_supply=0.0,
        source_system="TEST",
        batch_id="batch-001",
        ingested_at=datetime(2026, 4, 1, 8, 0, 0),
        vendor_id=vendor_id,
        region=region,
        category=category,
    )


def _make_triage_result(
    exception_id: str = "exc-001",
    priority: Priority = Priority.MEDIUM,
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Test root cause",
        recommended_action="Take test action",
        financial_impact_statement="Minor financial impact",
        planner_brief="Test planner brief",
    )


def _make_config(pattern_threshold: int = 3) -> AppConfig:
    config = AppConfig()
    config.agent.pattern_threshold = pattern_threshold
    return config


def _make_llm_pattern_response(patterns: list) -> MagicMock:
    """Build a mock LLM response returning the given list of pattern dicts."""
    resp = MagicMock()
    resp.text = json.dumps(patterns)
    resp.input_tokens = 50
    resp.output_tokens = 30
    return resp


def _vendor_pattern_dict(
    group_key: str = "VND-001",
    count: int = 3,
    description: str = "Vendor pattern",
) -> dict:
    return {
        "pattern_type": "VENDOR",
        "group_key": group_key,
        "count": count,
        "description": description,
    }


class TestPatternAnalyzerInit:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_init_calls_get_provider_with_agent_config(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        config = _make_config()
        from src.agent.pattern_analyzer import PatternAnalyzer
        PatternAnalyzer(config)
        mock_get_provider.assert_called_once_with(config.agent)

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_init_stores_config(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        config = _make_config(pattern_threshold=5)
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(config)
        assert analyzer._config.agent.pattern_threshold == 5


class TestBuildAggregates:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_counts_exceptions_by_vendor(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [
            _make_triage_result("exc-001", Priority.CRITICAL),
            _make_triage_result("exc-002", Priority.HIGH),
            _make_triage_result("exc-003", Priority.MEDIUM),
        ]
        enriched = [
            _make_enriched_exception("exc-001", vendor_id="VND-001"),
            _make_enriched_exception("exc-002", vendor_id="VND-001"),
            _make_enriched_exception("exc-003", vendor_id="VND-001"),
        ]
        aggs = analyzer._build_aggregates(triage, enriched)

        assert "VND-001" in aggs["vendor"]
        assert aggs["vendor"]["VND-001"]["count"] == 3
        assert aggs["vendor"]["VND-001"]["critical_count"] == 1
        assert aggs["vendor"]["VND-001"]["high_count"] == 1

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_counts_exceptions_by_region(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result(f"exc-{i:03d}") for i in range(3)]
        enriched = [
            _make_enriched_exception(f"exc-{i:03d}", region="Southeast") for i in range(3)
        ]
        aggs = analyzer._build_aggregates(triage, enriched)

        assert aggs["region"]["Southeast"]["count"] == 3

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_counts_exceptions_by_category(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result(f"exc-{i:03d}") for i in range(4)]
        enriched = [
            _make_enriched_exception(f"exc-{i:03d}", category="Frozen Foods") for i in range(4)
        ]
        aggs = analyzer._build_aggregates(triage, enriched)

        assert aggs["category"]["Frozen Foods"]["count"] == 4

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_skips_none_vendor(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result("exc-001")]
        enriched = [_make_enriched_exception("exc-001", vendor_id=None)]
        aggs = analyzer._build_aggregates(triage, enriched)

        assert len(aggs["vendor"]) == 0

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_exception_ids_aligned_by_position(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result("exc-A"), _make_triage_result("exc-B")]
        enriched = [
            _make_enriched_exception("exc-A", vendor_id="VND-100"),
            _make_enriched_exception("exc-B", vendor_id="VND-200"),
        ]
        aggs = analyzer._build_aggregates(triage, enriched)

        assert aggs["vendor"]["VND-100"]["count"] == 1
        assert aggs["vendor"]["VND-200"]["count"] == 1


class TestBuildSummaryPrompt:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_includes_qualifying_vendor_section(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer

        aggregates = {
            "vendor": {"VND-001": {"count": 5, "critical_count": 2, "high_count": 1, "exception_ids": []}},
            "region": {},
            "category": {},
            "dc": {},
        }
        prompt = PatternAnalyzer._build_summary_prompt(aggregates, threshold=3)

        assert "BY VENDOR:" in prompt
        assert "VND-001" in prompt
        assert "5 exceptions" in prompt
        assert "2 CRITICAL" in prompt

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_omits_sections_below_threshold(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer

        aggregates = {
            "vendor": {"VND-001": {"count": 2, "critical_count": 0, "high_count": 0, "exception_ids": []}},
            "region": {},
            "category": {},
            "dc": {},
        }
        prompt = PatternAnalyzer._build_summary_prompt(aggregates, threshold=3)

        assert "BY VENDOR:" not in prompt
        assert "VND-001" not in prompt

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_includes_category_section(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer

        aggregates = {
            "vendor": {},
            "region": {},
            "category": {"Frozen Foods": {"count": 4, "critical_count": 0, "high_count": 2, "exception_ids": []}},
            "dc": {},
        }
        prompt = PatternAnalyzer._build_summary_prompt(aggregates, threshold=3)

        assert "BY CATEGORY:" in prompt
        assert "Frozen Foods" in prompt

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_includes_region_section(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer

        aggregates = {
            "vendor": {},
            "region": {"Southeast": {"count": 6, "critical_count": 1, "high_count": 3, "exception_ids": []}},
            "category": {},
            "dc": {},
        }
        prompt = PatternAnalyzer._build_summary_prompt(aggregates, threshold=3)

        assert "BY REGION:" in prompt
        assert "Southeast" in prompt

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_includes_return_instruction(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer

        aggregates = {
            "vendor": {"V": {"count": 3, "critical_count": 0, "high_count": 0, "exception_ids": []}},
            "region": {}, "category": {}, "dc": {},
        }
        prompt = PatternAnalyzer._build_summary_prompt(aggregates, threshold=3)

        assert "JSON array" in prompt


class TestCallLlm:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_parsed_pattern_list(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_provider.complete.return_value = _make_llm_pattern_response(
            [_vendor_pattern_dict()]
        )
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        result = analyzer._call_llm("test prompt")

        assert len(result) == 1
        assert result[0]["pattern_type"] == "VENDOR"
        assert result[0]["group_key"] == "VND-001"

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_empty_list_on_llm_returning_empty_array(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_provider.complete.return_value = _make_llm_pattern_response([])
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        result = analyzer._call_llm("test prompt")

        assert result == []

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_empty_list_on_invalid_json(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        bad_resp = MagicMock()
        bad_resp.text = "not json at all"
        mock_provider.complete.return_value = bad_resp
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        result = analyzer._call_llm("test prompt")

        assert result == []

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_strips_markdown_fences(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        raw = json.dumps([_vendor_pattern_dict()])
        fenced = MagicMock()
        fenced.text = f"```json\n{raw}\n```"
        mock_provider.complete.return_value = fenced
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        result = analyzer._call_llm("test prompt")

        assert len(result) == 1

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_empty_list_when_llm_returns_non_list(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        bad_resp = MagicMock()
        bad_resp.text = '{"key": "value"}'
        mock_provider.complete.return_value = bad_resp
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        result = analyzer._call_llm("test prompt")

        assert result == []

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_empty_list_on_provider_exception(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_provider.complete.side_effect = RuntimeError("Network error")
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        result = analyzer._call_llm("test prompt")

        assert result == []


class TestApplyEscalations:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_escalates_medium_to_high_for_vendor_pattern(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [
            _make_triage_result("exc-001", Priority.MEDIUM),
            _make_triage_result("exc-002", Priority.MEDIUM),
            _make_triage_result("exc-003", Priority.HIGH),
        ]
        enriched = [
            _make_enriched_exception("exc-001", vendor_id="VND-001"),
            _make_enriched_exception("exc-002", vendor_id="VND-001"),
            _make_enriched_exception("exc-003", vendor_id="VND-001"),
        ]
        pattern = PatternDetail(
            pattern_id="PAT-AAAAAAAA",
            pattern_type=PatternType.VENDOR,
            group_key="VND-001",
            affected_count=3,
            description="Vendor issue",
        )
        report = MacroPatternReport(patterns=[pattern])

        count = analyzer._apply_escalations(report, triage, enriched)

        assert count == 2
        assert triage[0].priority == Priority.HIGH
        assert triage[0].escalated_from == "MEDIUM"
        assert triage[0].pattern_id == "PAT-AAAAAAAA"
        assert triage[1].priority == Priority.HIGH
        assert triage[2].priority == Priority.HIGH
        assert triage[2].escalated_from is None

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_does_not_downgrade_critical(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result("exc-001", Priority.CRITICAL)]
        enriched = [_make_enriched_exception("exc-001", vendor_id="VND-001")]
        pattern = PatternDetail(
            pattern_id="PAT-AAAAAAAA",
            pattern_type=PatternType.VENDOR,
            group_key="VND-001",
            affected_count=1,
            description="test",
        )
        report = MacroPatternReport(patterns=[pattern])

        count = analyzer._apply_escalations(report, triage, enriched)

        assert count == 0
        assert triage[0].priority == Priority.CRITICAL

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_does_not_escalate_low_priority(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result("exc-001", Priority.LOW)]
        enriched = [_make_enriched_exception("exc-001", vendor_id="VND-001")]
        pattern = PatternDetail(
            pattern_id="PAT-AAAAAAAA",
            pattern_type=PatternType.VENDOR,
            group_key="VND-001",
            affected_count=1,
            description="test",
        )
        report = MacroPatternReport(patterns=[pattern])

        count = analyzer._apply_escalations(report, triage, enriched)

        assert count == 0
        assert triage[0].priority == Priority.LOW

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_sets_pattern_id_on_all_members_even_non_escalated(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [
            _make_triage_result("exc-001", Priority.HIGH),
            _make_triage_result("exc-002", Priority.MEDIUM),
        ]
        enriched = [
            _make_enriched_exception("exc-001", vendor_id="VND-001"),
            _make_enriched_exception("exc-002", vendor_id="VND-001"),
        ]
        pattern = PatternDetail(
            pattern_id="PAT-BBBBBBBB",
            pattern_type=PatternType.VENDOR,
            group_key="VND-001",
            affected_count=2,
            description="test",
        )
        report = MacroPatternReport(patterns=[pattern])
        analyzer._apply_escalations(report, triage, enriched)

        assert triage[0].pattern_id == "PAT-BBBBBBBB"
        assert triage[1].pattern_id == "PAT-BBBBBBBB"


class TestAnalyze:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_empty_report_for_empty_triage_results(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        report = analyzer.analyze([], [])

        assert isinstance(report, MacroPatternReport)
        assert report.patterns == []
        assert report.total_patterns == 0

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_returns_empty_report_when_no_group_meets_threshold(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config(pattern_threshold=3))

        triage = [_make_triage_result(f"exc-{i:03d}") for i in range(2)]
        enriched = [_make_enriched_exception(f"exc-{i:03d}", vendor_id="VND-001") for i in range(2)]

        report = analyzer.analyze(triage, enriched)

        mock_provider.complete.assert_not_called()
        assert report.total_patterns == 0

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_full_flow_identifies_vendor_pattern_and_escalates(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_provider.complete.return_value = _make_llm_pattern_response(
            [_vendor_pattern_dict("VND-400", count=3, description="Vendor capacity issue")]
        )
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config(pattern_threshold=3))

        triage = [
            _make_triage_result("exc-001", Priority.MEDIUM),
            _make_triage_result("exc-002", Priority.MEDIUM),
            _make_triage_result("exc-003", Priority.HIGH),
        ]
        enriched = [
            _make_enriched_exception("exc-001", vendor_id="VND-400"),
            _make_enriched_exception("exc-002", vendor_id="VND-400"),
            _make_enriched_exception("exc-003", vendor_id="VND-400"),
        ]
        report = analyzer.analyze(triage, enriched)

        assert report.total_patterns == 1
        assert report.patterns[0].pattern_type == PatternType.VENDOR
        assert report.patterns[0].group_key == "VND-400"
        assert report.total_escalations == 2
        assert triage[0].priority == Priority.HIGH
        assert triage[0].escalated_from == "MEDIUM"
        assert triage[1].priority == Priority.HIGH
        assert triage[2].priority == Priority.HIGH

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_llm_not_called_when_results_empty(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        analyzer.analyze([], [])

        mock_provider.complete.assert_not_called()

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_llm_called_once_regardless_of_pattern_count(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_provider.complete.return_value = _make_llm_pattern_response([])
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config(pattern_threshold=2))

        triage = [_make_triage_result(f"exc-{i:03d}") for i in range(6)]
        enriched = [
            _make_enriched_exception(f"exc-{i:03d}", vendor_id="VND-001", region="Southeast", category="Dairy")
            for i in range(6)
        ]
        analyzer.analyze(triage, enriched)

        assert mock_provider.complete.call_count == 1
