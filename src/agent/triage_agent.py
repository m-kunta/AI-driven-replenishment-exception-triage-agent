"""Triage agent orchestrator (Task 5.4).

Coordinates the full Layer 3 pipeline:
  1. Batch processing (LLM inference)
  2. Phantom inventory webhook
  3. Macro pattern analysis
  4. Result assembly and statistics

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import List

from loguru import logger

from src.agent.batch_processor import BatchProcessor
from src.db.store import OverrideStore
from src.agent.pattern_analyzer import PatternAnalyzer
from src.agent.phantom_webhook import process_phantom_inventory
from src.models import (
    EnrichedExceptionSchema,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageRunResult,
)
from src.utils.config_loader import AppConfig


class TriageAgent:
    """Orchestrates the Layer 3 triage pipeline end-to-end.

    Instantiate once with AppConfig, then call run() for each batch of
    enriched exceptions. Components are instantiated in __init__ so they
    can be replaced with mocks in tests.
    """

    def __init__(
        self,
        config: AppConfig,
        override_store: OverrideStore | None = None,
    ) -> None:
        self.config = config
        self._batch_processor = BatchProcessor(config, override_store=override_store)
        self._pattern_analyzer = PatternAnalyzer(config)

    def run(self, enriched_exceptions: List[EnrichedExceptionSchema]) -> TriageRunResult:
        """Execute the full triage pipeline and return a TriageRunResult.

        Args:
            enriched_exceptions: All enriched records for this run, produced
                by the Layer 2 enrichment engine.

        Returns:
            TriageRunResult with all triage decisions, pattern report, and
            run statistics. Ready to be consumed by Layer 4.
        """
        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        run_timestamp = datetime.now(timezone.utc)
        run_date = date.today()

        logger.info(
            f"[{run_id}] Starting triage run: {len(enriched_exceptions)} exceptions"
        )

        # --- Step 1: Batch LLM inference ---
        batch_result = self._batch_processor.process(enriched_exceptions)
        triage_results = batch_result.triage_results

        logger.info(
            f"[{run_id}] Batch processing complete: "
            f"{batch_result.batches_completed} batches completed, "
            f"{batch_result.batches_failed} failed, "
            f"{len(triage_results)} results"
        )

        # --- Step 2: Phantom inventory webhook ---
        for result in triage_results:
            if "POTENTIAL_PHANTOM_INVENTORY" in result.compounding_risks:
                process_phantom_inventory(result, self.config.agent)

        phantom_flags = sum(1 for r in triage_results if r.phantom_flag)

        # --- Step 3: Macro pattern analysis (mutates triage_results in place) ---
        pattern_report: MacroPatternReport = self._pattern_analyzer.analyze(
            triage_results, enriched_exceptions
        )

        logger.info(
            f"[{run_id}] Pattern analysis complete: "
            f"{pattern_report.total_patterns} patterns, "
            f"{pattern_report.total_escalations} escalations"
        )

        # --- Step 4: Build statistics and return ---
        priority_counts = {p: 0 for p in Priority}
        for result in triage_results:
            priority_counts[result.priority] += 1

        pipeline_duration_seconds = round(
            (datetime.now(timezone.utc) - run_timestamp).total_seconds(), 2
        )

        statistics = RunStatistics(
            total_exceptions=len(triage_results),
            critical_count=priority_counts[Priority.CRITICAL],
            high_count=priority_counts[Priority.HIGH],
            medium_count=priority_counts[Priority.MEDIUM],
            low_count=priority_counts[Priority.LOW],
            batches_completed=batch_result.batches_completed,
            batches_failed=batch_result.batches_failed,
            pattern_escalations=pattern_report.total_escalations,
            phantom_flags=phantom_flags,
            total_input_tokens=batch_result.total_input_tokens,
            total_output_tokens=batch_result.total_output_tokens,
            pipeline_duration_seconds=pipeline_duration_seconds,
        )

        logger.info(
            f"[{run_id}] Triage run complete — "
            f"CRITICAL={statistics.critical_count} "
            f"HIGH={statistics.high_count} "
            f"MEDIUM={statistics.medium_count} "
            f"LOW={statistics.low_count} | "
            f"patterns={pattern_report.total_patterns} "
            f"escalations={pattern_report.total_escalations} "
            f"phantom_flags={phantom_flags} | "
            f"duration={pipeline_duration_seconds}s"
        )

        return TriageRunResult(
            run_id=run_id,
            run_date=run_date,
            triage_results=triage_results,
            pattern_report=pattern_report,
            statistics=statistics,
            run_timestamp=run_timestamp,
        )
