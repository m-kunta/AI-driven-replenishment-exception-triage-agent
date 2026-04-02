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
                # Validate alignment: LLM must return exactly the input exception IDs
                expected_ids = {ex.exception_id for ex in batch}
                returned_ids = {tr.exception_id for tr in triage_results}
                if expected_ids != returned_ids:
                    missing = sorted(expected_ids - returned_ids)
                    extra = sorted(returned_ids - expected_ids)
                    raise ValueError(
                        f"LLM returned misaligned results for batch of {len(batch)}: "
                        f"missing={missing}, extra={extra}"
                    )
                # Preserve positional alignment with the input batch for downstream passes.
                triage_by_id = {tr.exception_id: tr for tr in triage_results}
                triage_results = [triage_by_id[ex.exception_id] for ex in batch]
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
