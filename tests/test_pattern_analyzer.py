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
