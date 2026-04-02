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


class TestBatchProcessorProcess:
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_splits_7_exceptions_into_3_batches_with_size_3(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"])

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=3)
        processor = BatchProcessor(config)
        result = processor.process([_make_enriched_exception(f"exc-{i:03d}") for i in range(7)])

        assert mock_provider.complete.call_count == 3
        assert result.batches_completed == 3
        assert result.batches_failed == 0

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_splits_exactly_30_exceptions_into_1_batch(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"])

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=30)
        processor = BatchProcessor(config)
        result = processor.process([_make_enriched_exception(f"exc-{i:03d}") for i in range(30)])

        assert mock_provider.complete.call_count == 1
        assert result.batches_completed == 1

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_accumulates_token_counts_across_batches(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(
            ["exc-001"], input_tokens=200, output_tokens=80
        )

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=1)
        processor = BatchProcessor(config)
        result = processor.process([
            _make_enriched_exception("exc-001"),
            _make_enriched_exception("exc-002"),
        ])

        assert result.total_input_tokens == 400
        assert result.total_output_tokens == 160

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_collects_triage_results_from_all_batches(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"])

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=1)
        processor = BatchProcessor(config)
        result = processor.process([
            _make_enriched_exception("exc-001"),
            _make_enriched_exception("exc-002"),
        ])

        assert len(result.triage_results) == 2

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_stores_raw_pattern_analyses(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"], input_tokens=100, output_tokens=50)

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=1)
        processor = BatchProcessor(config)
        result = processor.process([_make_enriched_exception("exc-001")])

        assert len(result.raw_pattern_analyses) == 1
        assert result.raw_pattern_analyses[0]["_type"] == "pattern_analysis"

    def test_raises_value_error_on_empty_input(self):
        with patch("src.agent.batch_processor.get_provider"), \
             patch("src.agent.batch_processor.PromptComposer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.compose_system_prompt.return_value = "sys"

            from src.agent.batch_processor import BatchProcessor
            processor = BatchProcessor(AppConfig())

            with pytest.raises(ValueError, match="at least one exception"):
                processor.process([])


class TestBatchProcessorRetry:
    @patch("time.sleep")
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_retries_on_json_parse_failure_and_succeeds_on_third_attempt(
        self, mock_get_provider, mock_composer_cls, mock_sleep
    ):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"

        bad_resp = MagicMock()
        bad_resp.text = "not valid json ###"
        valid_resp = _mock_provider_response(["exc-001"])

        mock_provider.complete.side_effect = [bad_resp, bad_resp, valid_resp]

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(retry_attempts=3, retry_backoff_seconds=2)
        processor = BatchProcessor(config)
        result = processor.process([_make_enriched_exception("exc-001")])

        assert result.batches_completed == 1
        assert result.batches_failed == 0
        assert len(result.triage_results) == 1
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2)

    @patch("time.sleep")
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_marks_batch_failed_after_all_retries_exhausted(
        self, mock_get_provider, mock_composer_cls, mock_sleep
    ):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"

        bad_resp = MagicMock()
        bad_resp.text = "always invalid json ###"
        mock_provider.complete.return_value = bad_resp

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(retry_attempts=3)
        processor = BatchProcessor(config)
        result = processor.process([_make_enriched_exception("exc-001")])

        assert result.batches_failed == 1
        assert result.batches_completed == 0
        assert result.triage_results == []
        assert mock_provider.complete.call_count == 3

    @patch("time.sleep")
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_does_not_sleep_after_final_failed_attempt(
        self, mock_get_provider, mock_composer_cls, mock_sleep
    ):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"

        bad_resp = MagicMock()
        bad_resp.text = "bad json"
        mock_provider.complete.return_value = bad_resp

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(retry_attempts=3, retry_backoff_seconds=5)
        processor = BatchProcessor(config)
        processor.process([_make_enriched_exception("exc-001")])

        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_failed_batch_does_not_block_subsequent_batches(
        self, mock_get_provider, mock_composer_cls, mock_sleep
    ):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"

        bad_resp = MagicMock()
        bad_resp.text = "invalid"
        valid_resp = _mock_provider_response(["exc-001"])

        mock_provider.complete.side_effect = [bad_resp, valid_resp]

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=1, retry_attempts=1)
        processor = BatchProcessor(config)
        result = processor.process([
            _make_enriched_exception("exc-001"),
            _make_enriched_exception("exc-002"),
        ])

        assert result.batches_failed == 1
        assert result.batches_completed == 1
        assert len(result.triage_results) == 1


class TestReasoningTrace:
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_threads_reasoning_trace_enabled_true(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"])

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(reasoning_trace_enabled=True)
        processor = BatchProcessor(config)
        processor.process([_make_enriched_exception("exc-001")])

        call_args = mock_composer.compose_user_prompt.call_args
        assert call_args.kwargs.get("reasoning_trace_enabled") is True

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_reasoning_trace_disabled_by_default(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"])

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(reasoning_trace_enabled=False)
        processor = BatchProcessor(config)
        processor.process([_make_enriched_exception("exc-001")])

        call_args = mock_composer.compose_user_prompt.call_args
        assert call_args.kwargs.get("reasoning_trace_enabled") is False
