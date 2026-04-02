"""Tests for the BatchProcessor (Task 5.1).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    EnrichedExceptionSchema,
    EnrichmentConfidence,
    ExceptionType,
    Priority,
    TriageResult,
)
from src.utils.config_loader import AppConfig


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


def _make_config(
    batch_size: int = 30,
    retry_attempts: int = 3,
    retry_backoff_seconds: int = 5,
    reasoning_trace_enabled: bool = False,
) -> AppConfig:
    config = AppConfig()
    config.agent.batch_size = batch_size
    config.agent.retry_attempts = retry_attempts
    config.agent.retry_backoff_seconds = retry_backoff_seconds
    config.agent.reasoning_trace_enabled = reasoning_trace_enabled
    return config


def _make_llm_response_text(exception_ids: List[str], include_pattern: bool = True) -> str:
    """Build a minimal valid LLM JSON response string for the given exception IDs."""
    items = [
        {
            "exception_id": eid,
            "priority": "HIGH",
            "confidence": "HIGH",
            "root_cause": "Test root cause",
            "recommended_action": "Take test action",
            "financial_impact_statement": "Minor financial impact",
            "planner_brief": "Test planner brief",
            "compounding_risks": [],
            "missing_data_flags": [],
            "pattern_id": None,
            "escalated_from": None,
            "phantom_flag": False,
            "reasoning_trace": None,
        }
        for eid in exception_ids
    ]
    if include_pattern:
        items.append({
            "_type": "pattern_analysis",
            "vendor_summary": {},
            "dc_summary": {},
            "category_summary": {},
            "region_summary": {},
            "preliminary_patterns": [],
        })
    return json.dumps(items)


def _mock_provider_response(exception_ids: List[str], input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    resp = MagicMock()
    resp.text = _make_llm_response_text(exception_ids)
    resp.input_tokens = input_tokens
    resp.output_tokens = output_tokens
    return resp


class TestBatchProcessorInit:
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_init_calls_get_provider_with_agent_config(self, mock_get_provider, mock_composer_cls):
        mock_get_provider.return_value = MagicMock()
        mock_instance = MagicMock()
        mock_composer_cls.return_value = mock_instance
        mock_instance.compose_system_prompt.return_value = "sys"

        config = _make_config()
        from src.agent.batch_processor import BatchProcessor
        BatchProcessor(config)

        mock_get_provider.assert_called_once_with(config.agent)

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_init_passes_explicit_prompts_dir_to_composer(self, mock_get_provider, mock_composer_cls):
        mock_get_provider.return_value = MagicMock()
        mock_instance = MagicMock()
        mock_composer_cls.return_value = mock_instance
        mock_instance.compose_system_prompt.return_value = "sys"

        from src.agent.batch_processor import BatchProcessor, _PROMPTS_DIR
        BatchProcessor(_make_config())

        mock_composer_cls.assert_called_once_with(prompts_dir=_PROMPTS_DIR)

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_init_precomputes_system_prompt(self, mock_get_provider, mock_composer_cls):
        mock_get_provider.return_value = MagicMock()
        mock_instance = MagicMock()
        mock_composer_cls.return_value = mock_instance
        mock_instance.compose_system_prompt.return_value = "precomputed sys"

        from src.agent.batch_processor import BatchProcessor
        processor = BatchProcessor(_make_config())

        mock_instance.compose_system_prompt.assert_called_once()
        assert processor._system_prompt == "precomputed sys"

    def test_batch_processor_result_defaults(self):
        from src.agent.batch_processor import BatchProcessorResult
        result = BatchProcessorResult()
        assert result.triage_results == []
        assert result.raw_pattern_analyses == []
        assert result.batches_completed == 0
        assert result.batches_failed == 0
        assert result.total_input_tokens == 0
        assert result.total_output_tokens == 0


class TestParseResponse:
    def test_returns_triage_results_and_pattern_analysis(self):
        from src.agent.batch_processor import BatchProcessor
        text = _make_llm_response_text(["exc-001", "exc-002"])
        results, pattern = BatchProcessor._parse_response(text)

        assert len(results) == 2
        assert results[0].exception_id == "exc-001"
        assert results[1].exception_id == "exc-002"
        assert pattern is not None
        assert pattern["_type"] == "pattern_analysis"

    def test_pattern_analysis_not_in_triage_results(self):
        from src.agent.batch_processor import BatchProcessor
        text = _make_llm_response_text(["exc-001"])
        results, _ = BatchProcessor._parse_response(text)

        for r in results:
            assert isinstance(r, TriageResult)

    def test_returns_none_pattern_when_absent(self):
        from src.agent.batch_processor import BatchProcessor
        text = _make_llm_response_text(["exc-001"], include_pattern=False)
        results, pattern = BatchProcessor._parse_response(text)

        assert len(results) == 1
        assert results[0].exception_id == "exc-001"
        assert pattern is None

    def test_maps_priority_field(self):
        from src.agent.batch_processor import BatchProcessor
        text = _make_llm_response_text(["exc-001"])
        results, _ = BatchProcessor._parse_response(text)

        assert results[0].priority == Priority.HIGH

    def test_maps_confidence_field(self):
        from src.agent.batch_processor import BatchProcessor
        text = _make_llm_response_text(["exc-001"])
        results, _ = BatchProcessor._parse_response(text)

        assert results[0].confidence == EnrichmentConfidence.HIGH

    def test_extra_fields_are_ignored(self):
        from src.agent.batch_processor import BatchProcessor
        items = json.loads(_make_llm_response_text(["exc-001"]))
        items[0]["unexpected_llm_field"] = "should be dropped"
        results, _ = BatchProcessor._parse_response(json.dumps(items))

        assert results[0].exception_id == "exc-001"

    def test_strips_markdown_json_fence(self):
        from src.agent.batch_processor import BatchProcessor
        raw = _make_llm_response_text(["exc-001"])
        text = f"```json\n{raw}\n```"
        results, _ = BatchProcessor._parse_response(text)

        assert len(results) == 1
        assert results[0].exception_id == "exc-001"

    def test_strips_plain_markdown_fence(self):
        from src.agent.batch_processor import BatchProcessor
        raw = _make_llm_response_text(["exc-001"])
        text = f"```\n{raw}\n```"
        results, _ = BatchProcessor._parse_response(text)

        assert len(results) == 1

    def test_raises_json_decode_error_on_invalid_json(self):
        from src.agent.batch_processor import BatchProcessor
        with pytest.raises(json.JSONDecodeError):
            BatchProcessor._parse_response("not valid json at all")

    def test_raises_value_error_when_response_is_object_not_array(self):
        from src.agent.batch_processor import BatchProcessor
        with pytest.raises(ValueError, match="must be a JSON array"):
            BatchProcessor._parse_response('{"key": "value"}')

    def test_raises_value_error_when_no_triage_results_in_response(self):
        from src.agent.batch_processor import BatchProcessor
        only_pattern = json.dumps([{
            "_type": "pattern_analysis",
            "vendor_summary": {},
            "dc_summary": {},
            "category_summary": {},
            "region_summary": {},
            "preliminary_patterns": [],
        }])
        with pytest.raises(ValueError, match="no triage result objects"):
            BatchProcessor._parse_response(only_pattern)

    def test_raises_value_error_when_array_element_is_not_dict(self):
        from src.agent.batch_processor import BatchProcessor
        with pytest.raises(ValueError, match="Expected dict elements"):
            BatchProcessor._parse_response(json.dumps(["not", "dicts"]))
