"""Main pipeline orchestrator (Task 7.1).

Wires all four pipeline layers together into a single callable function
that can be invoked from scripts/run_triage.py or from tests.

Pipeline flow:
    Layer 1: CSVAdapter  → Normalizer       → List[CanonicalException]
    Layer 2: DataLoader  → EnrichmentEngine → List[EnrichedExceptionSchema]
    Layer 3: TriageAgent.run()              → TriageRunResult
    Layer 4: PriorityRouter → AlertDispatcher → BriefingGenerator → ExceptionLogger

dry_run mode stops after Layer 2 and prints an enrichment summary.
no_alerts mode runs Layers 1-4 but skips AlertDispatcher.dispatch().
sample mode forces the CSV path to data/sample/exceptions_sample.csv.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

from loguru import logger

from src.agent.triage_agent import TriageAgent
from src.enrichment.data_loader import DataLoader
from src.enrichment.engine import EnrichmentEngine
from src.ingestion.csv_adapter import CsvIngestionAdapter
from src.ingestion.normalizer import Normalizer
from src.models import EnrichedExceptionSchema, TriageRunResult
from src.output.alert_dispatcher import AlertDispatcher
from src.output.briefing_generator import BriefingGenerator
from src.output.exception_logger import ExceptionLogger
from src.output.router import PriorityRouter
from src.utils.config_loader import AppConfig, load_config, validate_required_env_vars

# Path to sample data (relative to project root)
_SAMPLE_CSV_PATH = "data/sample/exceptions_sample.csv"

# Guard flag so _configure_logging only removes the default sink once.
_logging_configured = False


def run_triage_pipeline(
    config_path: str = "config/config.yaml",
    run_date: Optional[str] = None,
    dry_run: bool = False,
    no_alerts: bool = False,
    sample: bool = False,
    verbose: bool = False,
) -> Optional[TriageRunResult]:
    """Execute the full replenishment exception triage pipeline.

    Args:
        config_path: Path to config YAML file.
        run_date:    ISO date string (YYYY-MM-DD) for the run. Defaults to today.
        dry_run:     If True, runs Layers 1-2 only and prints an enrichment
                     summary. No AI calls, no alerts, no output files.
        no_alerts:   If True, runs the full pipeline but skips alert dispatch.
        sample:      If True, forces the CSV ingestion path to the sample dataset
                     regardless of what config.yaml specifies.
        verbose:     If True, sets loguru level to DEBUG.

    Returns:
        TriageRunResult if the full pipeline ran; None in dry-run mode.
    """
    _configure_logging(verbose)

    # ------------------------------------------------------------------
    # Load config
    # ------------------------------------------------------------------
    config: AppConfig = load_config(config_path)
    validate_required_env_vars(config, adapter=config.ingestion.adapter)

    if sample:
        config.ingestion.csv.path = _SAMPLE_CSV_PATH
        logger.info("--sample flag: forcing CSV path to %s", _SAMPLE_CSV_PATH)

    # ------------------------------------------------------------------
    # Layer 1 — Ingestion & Normalisation
    # ------------------------------------------------------------------
    logger.info("=== Layer 1: Ingestion & Normalisation ===")
    adapter = CsvIngestionAdapter(
        file_path=config.ingestion.csv.path,
        delimiter=config.ingestion.csv.delimiter,
    )
    raw_records = adapter.fetch()
    logger.info("Fetched %d raw records from %s", len(raw_records), config.ingestion.csv.path)

    normalizer = Normalizer(
        field_mapping=config.ingestion.field_mapping,
        quarantine_dir=config.output.log_dir,
    )
    canonical_exceptions, quarantined_count = normalizer.normalize(raw_records)
    logger.info(
        "Normalisation complete: %d valid, %d quarantined",
        len(canonical_exceptions),
        quarantined_count,
    )

    if not canonical_exceptions:
        logger.warning("No valid exceptions after normalisation — nothing to triage.")
        _print_enrichment_summary([], config)
        return None

    # ------------------------------------------------------------------
    # Layer 2 — Context Enrichment
    # ------------------------------------------------------------------
    logger.info("=== Layer 2: Context Enrichment ===")
    reference_date = date.fromisoformat(run_date) if run_date else date.today()
    loaded_data = DataLoader(config=config.enrichment).load()
    engine = EnrichmentEngine(
        loaded_data,
        reference_date=reference_date,
        null_threshold_low=config.enrichment.null_threshold_low_confidence,
        null_threshold_medium=config.enrichment.null_threshold_medium_confidence,
        promo_lift_factor=config.enrichment.promo_lift_factor,
    )
    enriched_exceptions = engine.enrich(canonical_exceptions)
    logger.info("Enrichment complete: %d exceptions enriched", len(enriched_exceptions))

    _print_enrichment_summary(enriched_exceptions, config)

    if dry_run:
        logger.info("--dry-run flag: stopping after Layer 2.")
        return None

    # ------------------------------------------------------------------
    # Layer 3 — AI Triage (reasoning engine)
    # ------------------------------------------------------------------
    logger.info("=== Layer 3: AI Triage ===")
    triage_agent = TriageAgent(config)
    run_result: TriageRunResult = triage_agent.run(enriched_exceptions)

    logger.info(
        "Triage complete: CRITICAL=%d HIGH=%d MEDIUM=%d LOW=%d | "
        "patterns=%d escalations=%d phantom_flags=%d | duration=%.1fs",
        run_result.statistics.critical_count,
        run_result.statistics.high_count,
        run_result.statistics.medium_count,
        run_result.statistics.low_count,
        run_result.pattern_report.total_patterns,
        run_result.pattern_report.total_escalations,
        run_result.statistics.phantom_flags,
        run_result.statistics.pipeline_duration_seconds,
    )

    # ------------------------------------------------------------------
    # Layer 4 — Routing, Alerting & Output
    # ------------------------------------------------------------------
    logger.info("=== Layer 4: Output ===")

    # 4a — Route into priority queue files
    router = PriorityRouter(config)
    queue_paths = router.route(run_result)
    for priority, path in queue_paths.items():
        logger.info("  Queue file: %s → %s", priority.value, path)

    # 4b — Dispatch alerts (skip if --no-alerts)
    if no_alerts:
        logger.info("--no-alerts flag: skipping AlertDispatcher.")
    else:
        dispatcher = AlertDispatcher(config)
        dispatcher.dispatch(run_result)

    # 4c — Generate morning briefing
    briefing_gen = BriefingGenerator(config)
    briefing_path = briefing_gen.generate(run_result)
    logger.info("Morning briefing written to %s", briefing_path)

    # 4d — Append to exception audit log
    exc_logger = ExceptionLogger(config)
    log_path = exc_logger.log(run_result)
    logger.info("Exception audit log updated: %s", log_path)

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    _print_run_summary(run_result, briefing_path, log_path)

    return run_result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool) -> None:
    """Configure loguru sink with the requested verbosity level.

    Removes the default loguru sink on the first call only, so that
    programmatic callers (tests, web services) that installed their own
    sinks are not affected on subsequent invocations.
    """
    global _logging_configured
    if not _logging_configured:
        logger.remove()
        _logging_configured = True
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )


def _print_enrichment_summary(
    enriched: list[EnrichedExceptionSchema],
    config: AppConfig,
) -> None:
    """Print a human-readable enrichment summary to stdout."""
    total = len(enriched)
    if total == 0:
        print("\n[Enrichment Summary] — 0 exceptions enriched.\n")
        return

    confidence_counts = Counter(e.enrichment_confidence.value for e in enriched)
    promo_count = sum(1 for e in enriched if e.promo_active)
    total_exposure = sum(e.est_lost_sales_value or 0.0 for e in enriched)

    print("\n" + "─" * 56)
    print("  ENRICHMENT SUMMARY")
    print("─" * 56)
    print(f"  Exceptions enriched : {total}")
    print(f"  Confidence HIGH     : {confidence_counts.get('HIGH', 0)}")
    print(f"  Confidence MEDIUM   : {confidence_counts.get('MEDIUM', 0)}")
    print(f"  Confidence LOW      : {confidence_counts.get('LOW', 0)}")
    print(f"  On active promo     : {promo_count}")
    print(f"  Total est. exposure : ${total_exposure:,.0f}")
    print("─" * 56 + "\n")


def _print_run_summary(
    run_result: TriageRunResult,
    briefing_path: Path,
    log_path: Path,
) -> None:
    """Print a concise post-run summary table to stdout."""
    s = run_result.statistics
    total_exposure = sum(
        r.est_lost_sales_value or 0.0 for r in run_result.triage_results
    )

    print("\n" + "═" * 56)
    print("  TRIAGE RUN COMPLETE")
    print("═" * 56)
    print(f"  Run ID      : {run_result.run_id}")
    print(f"  Run date    : {run_result.run_date}")
    print(f"  Duration    : {s.pipeline_duration_seconds:.1f}s")
    print("─" * 56)
    print(f"  🔴 CRITICAL : {s.critical_count}")
    print(f"  🟠 HIGH     : {s.high_count}")
    print(f"  🟡 MEDIUM   : {s.medium_count}")
    print(f"  🟢 LOW      : {s.low_count}")
    print(f"  TOTAL       : {s.total_exceptions}")
    print("─" * 56)
    print(f"  Exposure    : ${total_exposure:,.0f}")
    print(f"  Patterns    : {run_result.pattern_report.total_patterns}")
    print(f"  Escalations : {s.pattern_escalations}")
    print(f"  Phantom     : {s.phantom_flags}")
    print("─" * 56)
    print(f"  Briefing    : {briefing_path}")
    print(f"  Audit log   : {log_path}")
    print("═" * 56 + "\n")
