# Batch Processor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/agent/batch_processor.py` — the core AI engine that splits enriched exceptions into batches, calls the configured LLM provider, parses JSON triage results, retries on parse failure, and returns structured output for downstream processing.

**Architecture:** `BatchProcessor` wraps `get_provider()` + `PromptComposer` into a single processing unit. It exposes one public method: `process(exceptions) -> BatchProcessorResult`. Internally it splits the input list into chunks of `config.agent.batch_size`, calls the LLM for each chunk, parses the JSON array response (stripping the trailing `pattern_analysis` element), and retries up to `config.agent.retry_attempts` times on any parse failure before marking the batch as failed and continuing.

**Tech Stack:** Python 3.9+, Pydantic v2, loguru, `src.agent.llm_provider.get_provider`, `src.agent.prompt_composer.PromptComposer`, `src.models.{EnrichedExceptionSchema,TriageResult}`, `src.utils.config_loader.AppConfig`, `time.sleep` for retry backoff.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/agent/batch_processor.py` | `BatchProcessorResult` dataclass + `BatchProcessor` class |
| Create | `tests/test_batch_processor.py` | All unit tests (mocked provider + composer) |

`BatchProcessor` has three methods:
- `__init__(config: AppConfig)` — initializes provider, composer, and pre-computes system prompt
- `process(exceptions: List[EnrichedExceptionSchema]) -> BatchProcessorResult` — public API; splits input and iterates batches
- `_process_batch(batch) -> tuple` — one LLM call with retry loop (private)
- `_parse_response(text: str) -> tuple` — static; strips fences, parses JSON, separates pattern_analysis (private)

`_parse_response` is `@staticmethod` so it can be tested without any mocking.

---

## Shared Test Helpers

These helpers are used across multiple tasks. Define them once at the top of `tests/test_batch_processor.py`.

```python
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
```

---

## Task 1: BatchProcessorResult dataclass + BatchProcessor.__init__

**Files:**
- Create: `src/agent/batch_processor.py`
- Create: `tests/test_batch_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_batch_processor.py` (after the shared helpers):

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/MKunta/AGENTS/CODE/AI-driven-replenishment-exception-triage-agent
source .venv/bin/activate
pytest tests/test_batch_processor.py::TestBatchProcessorInit -v
```

Expected: `ModuleNotFoundError: No module named 'src.agent.batch_processor'`

- [ ] **Step 3: Write the minimal implementation**

Create `src/agent/batch_processor.py`:

```python
"""Batch processor for the triage agent (Task 5.1).

Splits enriched exceptions into batches, calls the LLM provider,
parses JSON triage results, and retries on parse failure.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

from src.agent.llm_provider import LLMProvider, get_provider
from src.agent.prompt_composer import PromptComposer
from src.models import EnrichedExceptionSchema, TriageResult
from src.utils.config_loader import AppConfig

# Explicit path — avoids cwd-relative resolution when run from arbitrary directories.
# src/agent/batch_processor.py → .parent = src/agent → .parent = src → .parent = project root
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


@dataclass
class BatchProcessorResult:
    """Output of a BatchProcessor.process() call."""

    triage_results: List[TriageResult] = field(default_factory=list)
    raw_pattern_analyses: List[dict] = field(default_factory=list)
    batches_completed: int = 0
    batches_failed: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class BatchProcessor:
    """Processes batches of enriched exceptions through the configured LLM provider.

    Responsibilities:
    - Split input into batches of config.agent.batch_size (default 30)
    - Compose system + user prompts via PromptComposer
    - Call LLMProvider.complete() and parse JSON response
    - Separate the trailing pattern_analysis element from TriageResult objects
    - Retry up to config.agent.retry_attempts on JSON parse failure
    - Accumulate token counts across all batches

    Usage:
        processor = BatchProcessor(config)
        result = processor.process(enriched_exceptions)
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._provider: LLMProvider = get_provider(config.agent)
        self._composer = PromptComposer(prompts_dir=_PROMPTS_DIR)
        self._system_prompt = self._composer.compose_system_prompt()

    def process(self, exceptions: List[EnrichedExceptionSchema]) -> BatchProcessorResult:
        """Process all exceptions through the LLM in batches.

        Args:
            exceptions: All enriched exceptions for this run.

        Returns:
            BatchProcessorResult with triage results, raw pattern analyses, and token stats.

        Raises:
            ValueError: If exceptions list is empty.
        """
        if not exceptions:
            raise ValueError(
                "BatchProcessor.process() requires at least one exception; received empty list."
            )

        result = BatchProcessorResult()
        batch_size = self._config.agent.batch_size
        batches = [
            exceptions[i : i + batch_size]
            for i in range(0, len(exceptions), batch_size)
        ]

        for batch in batches:
            triage_results, pattern_analysis, input_tokens, output_tokens = (
                self._process_batch(batch)
            )
            if triage_results is None:
                result.batches_failed += 1
            else:
                result.triage_results.extend(triage_results)
                if pattern_analysis is not None:
                    result.raw_pattern_analyses.append(pattern_analysis)
                result.batches_completed += 1
                result.total_input_tokens += input_tokens
                result.total_output_tokens += output_tokens

        return result

    def _process_batch(
        self, batch: List[EnrichedExceptionSchema]
    ) -> Tuple[Optional[List[TriageResult]], Optional[dict], int, int]:
        """Process a single batch with retry logic on parse failure.

        Returns:
            (triage_results, pattern_analysis, input_tokens, output_tokens)
            triage_results is None if all retry attempts failed.
        """
        user_prompt = self._composer.compose_user_prompt(
            batch,
            reasoning_trace_enabled=self._config.agent.reasoning_trace_enabled,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self._config.agent.retry_attempts + 1):
            try:
                response = self._provider.complete(self._system_prompt, user_prompt)
                triage_results, pattern_analysis = self._parse_response(response.text)
                logger.debug(
                    f"Batch of {len(batch)} parsed successfully "
                    f"(attempt {attempt}, {response.input_tokens} in / {response.output_tokens} out tokens)."
                )
                return triage_results, pattern_analysis, response.input_tokens, response.output_tokens
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    f"Batch parse failed (attempt {attempt}/{self._config.agent.retry_attempts}): {exc}"
                )
                if attempt < self._config.agent.retry_attempts:
                    time.sleep(self._config.agent.retry_backoff_seconds)

        logger.error(
            f"Batch of {len(batch)} failed after "
            f"{self._config.agent.retry_attempts} attempts. "
            f"Last error: {last_error}"
        )
        return None, None, 0, 0

    @staticmethod
    def _parse_response(text: str) -> Tuple[List[TriageResult], Optional[dict]]:
        """Parse LLM response text into TriageResult list and optional pattern_analysis.

        Strips markdown code fences if the LLM added them despite instructions.
        Separates the element with _type == "pattern_analysis" from triage results.

        Args:
            text: Raw LLM response string.

        Returns:
            (triage_results, pattern_analysis) — pattern_analysis is None if absent.

        Raises:
            json.JSONDecodeError: If text is not valid JSON after fence stripping.
            ValueError: If the parsed JSON is not a list, or contains no triage objects.
        """
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            # Remove opening fence line (```json or ```) and closing fence line (```)
            inner_lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            stripped = "\n".join(inner_lines)

        data = json.loads(stripped)

        if not isinstance(data, list):
            raise ValueError(
                f"LLM response must be a JSON array, got {type(data).__name__}. "
                "Check the output_contract prompt."
            )

        triage_results: List[TriageResult] = []
        pattern_analysis: Optional[dict] = None

        for item in data:
            if not isinstance(item, dict):
                raise ValueError(
                    f"Expected dict elements in JSON array, got {type(item).__name__}."
                )
            if item.get("_type") == "pattern_analysis":
                pattern_analysis = item
            else:
                triage_results.append(TriageResult.model_validate(item))

        if not triage_results:
            raise ValueError(
                "LLM response contained no triage result objects. "
                "Only a pattern_analysis element was found."
            )

        return triage_results, pattern_analysis
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_batch_processor.py::TestBatchProcessorInit -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/agent/batch_processor.py tests/test_batch_processor.py
git commit -m "feat: add BatchProcessor scaffold — init, BatchProcessorResult, _PROMPTS_DIR"
```

---

## Task 2: _parse_response — happy path

**Files:**
- Modify: `tests/test_batch_processor.py` — add `TestParseResponse` class

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batch_processor.py`:

```python
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

        # No result should have exception_id == None and _type key
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
        """TriageResult has extra='ignore' — unknown LLM fields should not raise."""
        from src.agent.batch_processor import BatchProcessor
        items = json.loads(_make_llm_response_text(["exc-001"]))
        items[0]["unexpected_llm_field"] = "should be dropped"
        results, _ = BatchProcessor._parse_response(json.dumps(items))

        assert results[0].exception_id == "exc-001"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_batch_processor.py::TestParseResponse -v
```

Expected: `ImportError` or `AttributeError` — `_parse_response` not yet defined (Task 1 added it; these tests should PASS after Task 1 if done in order — if running in isolation, expect failures until implementation is in place).

> **Note:** If you completed Task 1 in the same session, these tests may already pass — run them to verify. If they do, commit immediately and move to Task 3.

- [ ] **Step 3: Run tests to confirm they pass**

```bash
pytest tests/test_batch_processor.py::TestParseResponse -v
```

Expected: 6 PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/test_batch_processor.py
git commit -m "test: add _parse_response happy path tests"
```

---

## Task 3: _parse_response — fence stripping and error cases

**Files:**
- Modify: `tests/test_batch_processor.py` — add error-case tests to `TestParseResponse`

- [ ] **Step 1: Write the failing tests**

Add inside `TestParseResponse` class:

```python
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
        """Array contains only a pattern_analysis element — no triage items."""
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_batch_processor.py::TestParseResponse -v -k "fence or raises"
```

Expected: Tests for fence stripping and error cases should FAIL (not yet implemented if you haven't added `_parse_response`).

> **Note:** If Task 1 is complete, `_parse_response` is already implemented and these tests should pass. Run to confirm — if all pass, skip Step 3 and go directly to Step 4.

- [ ] **Step 3: Run all parse response tests**

```bash
pytest tests/test_batch_processor.py::TestParseResponse -v
```

Expected: All 12 tests PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/test_batch_processor.py
git commit -m "test: add _parse_response fence stripping and error case tests"
```

---

## Task 4: process() — batch splitting and token accumulation

**Files:**
- Modify: `tests/test_batch_processor.py` — add `TestBatchProcessorProcess` class

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batch_processor.py`:

```python
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

        # 7 exceptions / batch_size=3 → ceil(7/3) = 3 batches
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
        # Each of 2 batches returns 200 input / 80 output tokens
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

        assert result.total_input_tokens == 400   # 200 * 2 batches
        assert result.total_output_tokens == 160  # 80 * 2 batches

    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_collects_triage_results_from_all_batches(self, mock_get_provider, mock_composer_cls):
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"

        # Both batches return one triage result each
        mock_provider.complete.return_value = _mock_provider_response(["exc-001"])

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(batch_size=1)
        processor = BatchProcessor(config)
        result = processor.process([
            _make_enriched_exception("exc-001"),
            _make_enriched_exception("exc-002"),
        ])

        # 2 batches × 1 result each = 2 total triage results
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
        # Response includes pattern_analysis element
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_batch_processor.py::TestBatchProcessorProcess -v
```

Expected: FAILED — `process()` not yet implemented.

> **Note:** If Task 1 is complete, `process()` is already implemented. Run — if all pass, skip Step 3 and go to Step 4.

- [ ] **Step 3: Run all process tests**

```bash
pytest tests/test_batch_processor.py::TestBatchProcessorProcess -v
```

Expected: 6 PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/test_batch_processor.py
git commit -m "test: add process() batch splitting and token accumulation tests"
```

---

## Task 5: process() — retry logic

**Files:**
- Modify: `tests/test_batch_processor.py` — add `TestBatchProcessorRetry` class

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batch_processor.py`:

```python
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

        # Fail attempt 1, fail attempt 2, succeed attempt 3
        mock_provider.complete.side_effect = [bad_resp, bad_resp, valid_resp]

        from src.agent.batch_processor import BatchProcessor
        config = _make_config(retry_attempts=3, retry_backoff_seconds=2)
        processor = BatchProcessor(config)
        result = processor.process([_make_enriched_exception("exc-001")])

        assert result.batches_completed == 1
        assert result.batches_failed == 0
        assert len(result.triage_results) == 1
        # Sleep between attempt 1→2 and attempt 2→3 (not after the final successful attempt)
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
        # LLM called exactly retry_attempts times
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

        # 3 attempts → sleep between 1→2 and 2→3 only = 2 sleeps, NOT 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("src.agent.batch_processor.PromptComposer")
    @patch("src.agent.batch_processor.get_provider")
    def test_failed_batch_does_not_block_subsequent_batches(
        self, mock_get_provider, mock_composer_cls, mock_sleep
    ):
        """A failed batch increments batches_failed but remaining batches continue."""
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        mock_composer = MagicMock()
        mock_composer_cls.return_value = mock_composer
        mock_composer.compose_system_prompt.return_value = "sys"
        mock_composer.compose_user_prompt.return_value = "user"

        bad_resp = MagicMock()
        bad_resp.text = "invalid"
        valid_resp = _mock_provider_response(["exc-001"])

        # Batch 1 always fails all attempts; batch 2 succeeds on first try
        # With retry_attempts=1, batch 1 makes 1 call, batch 2 makes 1 call = 2 total
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_batch_processor.py::TestBatchProcessorRetry -v
```

Expected: FAILED — retry logic not yet in place.

> **Note:** If Task 1 implemented `_process_batch` with retry, these should pass. Run to verify.

- [ ] **Step 3: Run all retry tests**

```bash
pytest tests/test_batch_processor.py::TestBatchProcessorRetry -v
```

Expected: 4 PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/test_batch_processor.py
git commit -m "test: add retry logic tests for batch processor"
```

---

## Task 6: reasoning_trace threading + full suite green

**Files:**
- Modify: `tests/test_batch_processor.py` — add `TestReasoningTrace` class

- [ ] **Step 1: Write the failing test**

Add to `tests/test_batch_processor.py`:

```python
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
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
pytest tests/test_batch_processor.py::TestReasoningTrace -v
```

Expected: FAILED if `_process_batch` doesn't pass `reasoning_trace_enabled` as keyword.

> **Note:** If Task 1 implemented this correctly, they will pass immediately.

- [ ] **Step 3: Run the full test_batch_processor suite**

```bash
pytest tests/test_batch_processor.py -v
```

Expected: All tests PASSED (20+ tests)

- [ ] **Step 4: Run the full project test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: All 167+ tests PASSED (167 existing + new batch processor tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_batch_processor.py
git commit -m "test: add reasoning_trace threading tests; all tests green"
```

---

## Self-Review

**Spec coverage check:**

| Requirement (from CLAUDE.md / memory) | Task covering it |
|---------------------------------------|-----------------|
| Batches enriched exceptions, max 30 per batch | Task 4 |
| Calls LLM via `get_provider(config.agent)` | Task 1 |
| Passes `prompts_dir=Path(__file__).parent...` explicitly | Task 1 |
| Parses JSON triage results | Task 2 |
| Strips markdown fences | Task 3 |
| Retry logic on parse failure | Task 5 |
| Sleeps `retry_backoff_seconds` between attempts (not after final) | Task 5 |
| Marks batch as failed after max retries, continues remaining batches | Task 5 |
| Threads `reasoning_trace_enabled` to `compose_user_prompt()` | Task 6 |
| Pre-computes system prompt at init (not per-batch) | Task 1 |
| Accumulates token counts | Task 4 |
| Stores raw `pattern_analysis` objects separately | Task 4 |
| `BatchProcessorResult` with all stats fields | Task 1 |
| Raises `ValueError` on empty input | Task 4 |

**Placeholder scan:** None found — all steps contain complete code.

**Type consistency check:**
- `BatchProcessorResult` defined in Task 1, referenced in Task 4/5/6 ✓
- `_mock_provider_response` helper defined in shared section, used in Tasks 2–6 ✓
- `_make_llm_response_text` helper defined in shared section ✓
- `_parse_response` returns `Tuple[List[TriageResult], Optional[dict]]` — used consistently ✓
- `_process_batch` returns `Tuple[Optional[List[TriageResult]], Optional[dict], int, int]` ✓
- `compose_user_prompt(batch, reasoning_trace_enabled=...)` — kwarg name matches `prompt_composer.py:145` ✓
