"""Tests for the BatchProcessor (Task 5.1).

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


def _make_llm_response_text(exception_ids: list, include_pattern: bool = True) -> str:
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


def _mock_provider_response(exception_ids: list, input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
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
