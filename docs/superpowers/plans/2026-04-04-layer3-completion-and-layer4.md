# Layer 3 Completion + Layer 4 + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the replenishment exception triage pipeline — TriageAgent orchestrator, four output-layer modules, and a runnable CLI.

**Architecture:** TriageAgent (Task 1) wires BatchProcessor → phantom webhook → PatternAnalyzer into one `run()` call returning `TriageRunResult`. The output layer (Tasks 2–5) consumes `TriageRunResult` independently. `src/main.py` + `scripts/run_triage.py` (Task 6) wires all four layers end-to-end.

**Tech Stack:** Python 3.9+, Pydantic v2, loguru, httpx, smtplib (stdlib), threading (stdlib), argparse (stdlib), csv (stdlib)

---

## File Map

**Created:**
- `src/agent/triage_agent.py` — orchestrator: batch → phantom webhook → pattern analysis → RunStatistics
- `tests/test_triage_agent.py`
- `src/output/router.py` — routes TriageResult to 4 priority JSON queue files
- `tests/test_router.py`
- `src/output/exception_logger.py` — append CSV log, idempotent on (run_id, exception_id)
- `tests/test_exception_logger.py`
- `src/output/alert_dispatcher.py` — CRITICAL/HIGH alert dispatch via email/Slack/Teams/webhook + SLA timer
- `tests/test_alert_dispatcher.py`
- `src/output/briefing_generator.py` — markdown briefing with LLM executive summary section
- `tests/test_briefing_generator.py`
- `src/main.py` — `run_triage_pipeline()` full stack orchestration
- `scripts/run_triage.py` — argparse CLI
- `tests/test_main.py`

**Modified:** none — all output-layer modules are new files in an otherwise empty `src/output/`.

---

## Codebase Context for Implementers

All imports should use `from __future__ import annotations`. Tests mock at module import paths (e.g. `patch("src.agent.triage_agent.BatchProcessor")`).

**Key type facts (do not guess — use these exactly):**
- `TriageResult.confidence` → `EnrichmentConfidence` (not `Confidence`)
- `TriageResult.missing_data_flags` → `List[str]` (not `missing_data_fields`)
- `TriageResult.financial_impact_statement` → `str` (not `financial_impact`)
- `BatchProcessorResult` is a `@dataclass` from `src.agent.batch_processor`; fields: `triage_results`, `batches_completed`, `batches_failed`, `total_input_tokens`, `total_output_tokens`
- `TriageRunResult` fields: `run_id: str`, `run_date: date`, `triage_results: List[TriageResult]`, `pattern_report: MacroPatternReport`, `statistics: RunStatistics`, `run_timestamp: datetime`
- `RunStatistics` fields: `total_exceptions`, `critical_count`, `high_count`, `medium_count`, `low_count`, `batches_completed`, `batches_failed`, `pattern_escalations`, `phantom_flags`, `total_input_tokens`, `total_output_tokens`, `pipeline_duration_seconds`

**Ingestion API:**
- `CSVAdapter(file_path: str, delimiter: str = ",")` → `.fetch() -> List[Dict]`
- `Normalizer(field_mapping: dict = None, quarantine_dir: str = "output/logs")` → `.normalize(raw_records) -> (List[CanonicalException], int_quarantined)`

**Enrichment API:**
- `DataLoader(config=config.enrichment)` → `.load() -> LoadedData`
- `EnrichmentEngine(loaded_data, reference_date=None, null_threshold_low=3, null_threshold_medium=1, promo_lift_factor=1.4)` → `.enrich(canonical_exceptions) -> List[EnrichedExceptionSchema]`

**Config API:**
- `load_config(config_path: str = "config/config.yaml") -> AppConfig`
- `AppConfig.alerting.channels: List[AlertChannelConfig]` — `type`, `enabled`, `smtp_host`, `smtp_port`, `from_address`, `to_addresses`, `webhook_url`
- `AppConfig.alerting.critical_sla_minutes: int` (default 60)
- `AppConfig.alerting.secondary_escalation_contact: str`
- `AppConfig.output.briefing_dir: str` (default `"output/briefings"`)
- `AppConfig.output.log_dir: str` (default `"output/logs"`)
- `AppConfig.output.max_exceptions_in_briefing: int` (default 10)

**Run tests after each task:** `pytest tests/ -v` from the project root (`.venv` must be activated).

---

### Task 1: Triage Agent Orchestrator (`src/agent/triage_agent.py`)

**Files:**
- Create: `src/agent/triage_agent.py`
- Create: `tests/test_triage_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage_agent.py`:

```python
"""Tests for TriageAgent (Task 5.4)."""
from __future__ import annotations

from datetime import date, datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    EnrichedExceptionSchema,
    EnrichmentConfidence,
    ExceptionType,
    MacroPatternReport,
    Priority,
    TriageResult,
)
from src.utils.config_loader import AppConfig


def _make_enriched(exception_id: str = "exc-001") -> EnrichedExceptionSchema:
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


def _make_triage_result(
    exception_id: str, priority: Priority = Priority.HIGH
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Low vendor fill rate",
        recommended_action="Contact vendor",
        financial_impact_statement="$5,000 lost sales",
        planner_brief="Vendor underperforming for 30 days.",
    )


def _make_batch_result(triage_results: List[TriageResult]):
    from src.agent.batch_processor import BatchProcessorResult
    r = BatchProcessorResult()
    r.triage_results = list(triage_results)
    r.batches_completed = 1
    r.batches_failed = 0
    r.total_input_tokens = 100
    r.total_output_tokens = 50
    return r


@patch("src.agent.triage_agent.PatternAnalyzer")
@patch("src.agent.triage_agent.BatchProcessor")
@patch("src.agent.triage_agent.process_phantom_inventory")
def test_run_returns_triage_run_result(mock_webhook, MockBP, MockPA):
    """run() returns a TriageRunResult with expected structure."""
    exceptions = [_make_enriched("exc-001"), _make_enriched("exc-002")]
    triage_results = [
        _make_triage_result("exc-001", Priority.CRITICAL),
        _make_triage_result("exc-002", Priority.LOW),
    ]
    MockBP.return_value.process.return_value = _make_batch_result(triage_results)
    MockPA.return_value.analyze.return_value = MacroPatternReport()

    from src.agent.triage_agent import TriageAgent
    agent = TriageAgent(AppConfig())
    result = agent.run(exceptions)

    assert result.run_id
    assert result.run_date == date.today()
    assert len(result.triage_results) == 2
    assert result.statistics.total_exceptions == 2
    assert result.statistics.critical_count == 1
    assert result.statistics.low_count == 1
    assert result.statistics.batches_completed == 1


@patch("src.agent.triage_agent.PatternAnalyzer")
@patch("src.agent.triage_agent.BatchProcessor")
@patch("src.agent.triage_agent.process_phantom_inventory")
def test_run_calls_phantom_webhook_per_result(mock_webhook, MockBP, MockPA):
    """process_phantom_inventory is called once per triage result."""
    exceptions = [_make_enriched("exc-001"), _make_enriched("exc-002")]
    triage_results = [_make_triage_result("exc-001"), _make_triage_result("exc-002")]
    MockBP.return_value.process.return_value = _make_batch_result(triage_results)
    MockPA.return_value.analyze.return_value = MacroPatternReport()

    from src.agent.triage_agent import TriageAgent
    agent = TriageAgent(AppConfig())
    agent.run(exceptions)

    assert mock_webhook.call_count == 2


@patch("src.agent.triage_agent.PatternAnalyzer")
@patch("src.agent.triage_agent.BatchProcessor")
@patch("src.agent.triage_agent.process_phantom_inventory")
def test_run_counts_phantom_flags_in_statistics(mock_webhook, MockBP, MockPA):
    """statistics.phantom_flags counts TriageResults where phantom_flag is True."""
    exceptions = [_make_enriched("exc-001")]
    tr = _make_triage_result("exc-001")
    tr.phantom_flag = True
    MockBP.return_value.process.return_value = _make_batch_result([tr])
    MockPA.return_value.analyze.return_value = MacroPatternReport()

    from src.agent.triage_agent import TriageAgent
    agent = TriageAgent(AppConfig())
    result = agent.run(exceptions)

    assert result.statistics.phantom_flags == 1


@patch("src.agent.triage_agent.PatternAnalyzer")
@patch("src.agent.triage_agent.BatchProcessor")
@patch("src.agent.triage_agent.process_phantom_inventory")
def test_run_reflects_pattern_escalations(mock_webhook, MockBP, MockPA):
    """statistics.pattern_escalations matches MacroPatternReport.total_escalations."""
    exceptions = [_make_enriched("exc-001")]
    MockBP.return_value.process.return_value = _make_batch_result(
        [_make_triage_result("exc-001")]
    )
    MockPA.return_value.analyze.return_value = MacroPatternReport(
        total_patterns=1, total_escalations=3
    )

    from src.agent.triage_agent import TriageAgent
    agent = TriageAgent(AppConfig())
    result = agent.run(exceptions)

    assert result.statistics.pattern_escalations == 3


@patch("src.agent.triage_agent.PatternAnalyzer")
@patch("src.agent.triage_agent.BatchProcessor")
@patch("src.agent.triage_agent.process_phantom_inventory")
def test_run_passes_token_stats_through(mock_webhook, MockBP, MockPA):
    """Token counts from BatchProcessorResult flow into RunStatistics."""
    exceptions = [_make_enriched("exc-001")]
    batch_result = _make_batch_result([_make_triage_result("exc-001")])
    batch_result.total_input_tokens = 999
    batch_result.total_output_tokens = 333
    MockBP.return_value.process.return_value = batch_result
    MockPA.return_value.analyze.return_value = MacroPatternReport()

    from src.agent.triage_agent import TriageAgent
    agent = TriageAgent(AppConfig())
    result = agent.run(exceptions)

    assert result.statistics.total_input_tokens == 999
    assert result.statistics.total_output_tokens == 333
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_triage_agent.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `triage_agent` does not exist yet.

- [ ] **Step 3: Implement `src/agent/triage_agent.py`**

```python
"""Triage Agent orchestrator (Task 5.4).

Coordinates Pass 1 (batch processing), phantom webhook, and Pass 2 (pattern
analysis) into a single agentic run returning a TriageRunResult.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List

from loguru import logger

from src.agent.batch_processor import BatchProcessor
from src.agent.pattern_analyzer import PatternAnalyzer
from src.agent.phantom_webhook import process_phantom_inventory
from src.models import (
    EnrichedExceptionSchema,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)
from src.utils.config_loader import AppConfig


class TriageAgent:
    """Orchestrates the full AI triage pipeline for a single run."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._batch_processor = BatchProcessor(config)
        self._pattern_analyzer = PatternAnalyzer(config)

    def run(self, enriched_exceptions: List[EnrichedExceptionSchema]) -> TriageRunResult:
        """Execute the three-stage triage pipeline.

        Args:
            enriched_exceptions: All enriched exceptions for this run.

        Returns:
            TriageRunResult with all results, pattern report, and statistics.

        Raises:
            ValueError: If enriched_exceptions is empty (propagated from BatchProcessor).
        """
        run_id = str(uuid.uuid4())
        run_date = date.today()
        run_timestamp = datetime.now()

        logger.info(
            f"[{run_id}] Triage run started — {len(enriched_exceptions)} exceptions."
        )

        # Pass 1: batch processing
        batch_result = self._batch_processor.process(enriched_exceptions)
        triage_results: List[TriageResult] = batch_result.triage_results

        # Phantom webhook: fire for each flagged result, count confirmed phantoms
        phantom_count = 0
        for tr in triage_results:
            process_phantom_inventory(tr, self._config.agent)
            if tr.phantom_flag:
                phantom_count += 1

        # Pass 2: pattern analysis
        # Align enriched exceptions by exception_id — handles any failed batches
        enriched_by_id = {ex.exception_id: ex for ex in enriched_exceptions}
        aligned_enriched = [
            enriched_by_id[tr.exception_id]
            for tr in triage_results
            if tr.exception_id in enriched_by_id
        ]
        pattern_report: MacroPatternReport = self._pattern_analyzer.analyze(
            triage_results, aligned_enriched
        )

        # Assemble run statistics
        duration = (datetime.now() - run_timestamp).total_seconds()
        statistics = RunStatistics(
            total_exceptions=len(enriched_exceptions),
            critical_count=sum(
                1 for tr in triage_results if tr.priority == Priority.CRITICAL
            ),
            high_count=sum(
                1 for tr in triage_results if tr.priority == Priority.HIGH
            ),
            medium_count=sum(
                1 for tr in triage_results if tr.priority == Priority.MEDIUM
            ),
            low_count=sum(
                1 for tr in triage_results if tr.priority == Priority.LOW
            ),
            batches_completed=batch_result.batches_completed,
            batches_failed=batch_result.batches_failed,
            pattern_escalations=pattern_report.total_escalations,
            phantom_flags=phantom_count,
            total_input_tokens=batch_result.total_input_tokens,
            total_output_tokens=batch_result.total_output_tokens,
            pipeline_duration_seconds=duration,
        )

        result = TriageRunResult(
            run_id=run_id,
            run_date=run_date,
            triage_results=triage_results,
            pattern_report=pattern_report,
            statistics=statistics,
            run_timestamp=run_timestamp,
        )

        logger.info(
            f"[{run_id}] Triage run complete — "
            f"CRITICAL={statistics.critical_count} HIGH={statistics.high_count} "
            f"MEDIUM={statistics.medium_count} LOW={statistics.low_count} "
            f"patterns={pattern_report.total_patterns} "
            f"escalations={pattern_report.total_escalations} "
            f"phantoms={phantom_count} duration={duration:.2f}s"
        )
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_triage_agent.py -v
```

Expected: 5 tests pass. Example output:
```
tests/test_triage_agent.py::test_run_returns_triage_run_result PASSED
tests/test_triage_agent.py::test_run_calls_phantom_webhook_per_result PASSED
tests/test_triage_agent.py::test_run_counts_phantom_flags_in_statistics PASSED
tests/test_triage_agent.py::test_run_reflects_pattern_escalations PASSED
tests/test_triage_agent.py::test_run_passes_token_stats_through PASSED
5 passed
```

- [ ] **Step 5: Run full suite to verify nothing broke**

```bash
pytest tests/ -v --tb=short
```

Expected: all previously passing tests still pass plus the 5 new ones.

- [ ] **Step 6: Commit**

```bash
git add src/agent/triage_agent.py tests/test_triage_agent.py
git commit -m "feat: add TriageAgent orchestrator (Task 5.4)"
```

---

### Task 2: Priority Router (`src/output/router.py`)

**Files:**
- Create: `src/output/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_router.py`:

```python
"""Tests for PriorityRouter (Task 6.1)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)


def _make_triage_result(
    exception_id: str,
    priority: Priority,
    est_lost_sales_value: float = 0.0,
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="test",
        recommended_action="test",
        financial_impact_statement="test",
        planner_brief="test",
        est_lost_sales_value=est_lost_sales_value,
    )


def _make_run_result(triage_results) -> TriageRunResult:
    return TriageRunResult(
        run_id="run-001",
        run_date=date(2026, 4, 4),
        triage_results=triage_results,
        pattern_report=MacroPatternReport(),
        statistics=RunStatistics(),
        run_timestamp=datetime(2026, 4, 4, 8, 0, 0),
    )


def test_route_writes_four_files(tmp_path):
    """route() always writes exactly four priority files."""
    from src.output.router import PriorityRouter

    run_result = _make_run_result([
        _make_triage_result("exc-001", Priority.CRITICAL),
        _make_triage_result("exc-002", Priority.HIGH),
    ])
    router = PriorityRouter(log_dir=str(tmp_path))
    written = router.route(run_result)

    assert len(written) == 4
    for path in written.values():
        assert Path(path).exists()


def test_route_total_records_equals_input(tmp_path):
    """Total records across all four files equals the number of triage results."""
    from src.output.router import PriorityRouter

    triage_results = [
        _make_triage_result("exc-001", Priority.CRITICAL),
        _make_triage_result("exc-002", Priority.HIGH),
        _make_triage_result("exc-003", Priority.MEDIUM),
        _make_triage_result("exc-004", Priority.LOW),
        _make_triage_result("exc-005", Priority.HIGH),
    ]
    router = PriorityRouter(log_dir=str(tmp_path))
    written = router.route(_make_run_result(triage_results))

    total = sum(len(json.load(open(p))) for p in written.values())
    assert total == 5


def test_route_sorted_by_financial_value(tmp_path):
    """Within each priority file, records are sorted by est_lost_sales_value descending."""
    from src.output.router import PriorityRouter

    results = [
        _make_triage_result("exc-001", Priority.HIGH, est_lost_sales_value=100.0),
        _make_triage_result("exc-002", Priority.HIGH, est_lost_sales_value=500.0),
        _make_triage_result("exc-003", Priority.HIGH, est_lost_sales_value=250.0),
    ]
    router = PriorityRouter(log_dir=str(tmp_path))
    written = router.route(_make_run_result(results))

    with open(written[Priority.HIGH.value]) as f:
        data = json.load(f)

    values = [r["est_lost_sales_value"] for r in data]
    assert values == sorted(values, reverse=True)


def test_route_creates_nested_directory(tmp_path):
    """route() creates the log_dir if it does not exist."""
    from src.output.router import PriorityRouter

    nested = tmp_path / "deep" / "nested" / "logs"
    router = PriorityRouter(log_dir=str(nested))
    router.route(_make_run_result([]))

    assert nested.exists()


def test_route_empty_priority_writes_empty_array(tmp_path):
    """Priority files with no results contain an empty JSON array."""
    from src.output.router import PriorityRouter

    run_result = _make_run_result([_make_triage_result("exc-001", Priority.CRITICAL)])
    router = PriorityRouter(log_dir=str(tmp_path))
    written = router.route(run_result)

    with open(written[Priority.LOW.value]) as f:
        assert json.load(f) == []
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_router.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.output.router'`

- [ ] **Step 3: Implement `src/output/router.py`**

```python
"""Priority router for Layer 4 (Task 6.1).

Routes each TriageResult into a per-priority JSON file, sorted by financial
value descending within each tier.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from loguru import logger

from src.models import Priority, TriageResult, TriageRunResult


class PriorityRouter:
    """Routes triage results to per-priority JSON queue files."""

    def __init__(self, log_dir: str = "output/logs") -> None:
        self._log_dir = Path(log_dir)

    def route(self, run_result: TriageRunResult) -> Dict[str, Path]:
        """Write four priority queue files for this run.

        Args:
            run_result: Complete output of one triage pipeline run.

        Returns:
            Mapping of priority value (str) → written file Path.
        """
        self._log_dir.mkdir(parents=True, exist_ok=True)
        run_date_str = run_result.run_date.isoformat()

        queues: Dict[str, List[TriageResult]] = {
            Priority.CRITICAL.value: [],
            Priority.HIGH.value: [],
            Priority.MEDIUM.value: [],
            Priority.LOW.value: [],
        }
        for tr in run_result.triage_results:
            queues[tr.priority.value].append(tr)

        for tier_list in queues.values():
            tier_list.sort(key=lambda t: t.est_lost_sales_value or 0.0, reverse=True)

        written: Dict[str, Path] = {}
        for priority_val, tier_list in queues.items():
            path = self._log_dir / f"{priority_val}_{run_date_str}.json"
            with path.open("w", encoding="utf-8") as f:
                json.dump(
                    [tr.model_dump(mode="json") for tr in tier_list],
                    f,
                    indent=2,
                )
            written[priority_val] = path
            logger.debug(
                f"PriorityRouter: wrote {len(tier_list)} {priority_val} "
                f"exceptions to {path}."
            )

        logger.info(
            f"PriorityRouter: routed {len(run_result.triage_results)} exceptions "
            f"across 4 priority queues in {self._log_dir}."
        )
        return written
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_router.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/output/router.py tests/test_router.py
git commit -m "feat: add PriorityRouter for Layer 4 (Task 6.1)"
```

---

### Task 3: Exception Logger (`src/output/exception_logger.py`)

**Files:**
- Create: `src/output/exception_logger.py`
- Create: `tests/test_exception_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exception_logger.py`:

```python
"""Tests for ExceptionLogger (Task 6.4)."""
from __future__ import annotations

import csv
from datetime import date, datetime

import pytest

from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)


def _make_triage_result(
    exception_id: str = "exc-001", priority: Priority = Priority.HIGH
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Low vendor fill rate",
        recommended_action="Contact vendor",
        financial_impact_statement="$5,000 lost sales",
        planner_brief="Vendor underperforming.",
    )


def _make_run_result(run_id: str, triage_results) -> TriageRunResult:
    return TriageRunResult(
        run_id=run_id,
        run_date=date(2026, 4, 4),
        triage_results=triage_results,
        pattern_report=MacroPatternReport(),
        statistics=RunStatistics(),
        run_timestamp=datetime(2026, 4, 4, 8, 0, 0),
    )


def test_log_writes_csv_with_correct_header(tmp_path):
    """log() creates a CSV with all expected column headers on first write."""
    from src.output.exception_logger import ExceptionLogger, _CSV_FIELDNAMES

    el = ExceptionLogger(log_dir=str(tmp_path))
    el.log(_make_run_result("run-001", [_make_triage_result()]))

    with open(tmp_path / "exception_log.csv") as f:
        reader = csv.DictReader(f)
        assert list(reader.fieldnames) == _CSV_FIELDNAMES


def test_log_writes_one_row_per_triage_result(tmp_path):
    """log() writes exactly one row per triage result."""
    from src.output.exception_logger import ExceptionLogger

    results = [_make_triage_result(f"exc-{i:03d}") for i in range(5)]
    el = ExceptionLogger(log_dir=str(tmp_path))
    rows_written = el.log(_make_run_result("run-001", results))

    assert rows_written == 5
    with open(tmp_path / "exception_log.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5


def test_log_is_idempotent_on_same_run_id(tmp_path):
    """Calling log() twice with the same run_id writes 0 rows the second time."""
    from src.output.exception_logger import ExceptionLogger

    el = ExceptionLogger(log_dir=str(tmp_path))
    el.log(_make_run_result("run-001", [_make_triage_result()]))
    rows_written = el.log(_make_run_result("run-001", [_make_triage_result()]))

    assert rows_written == 0
    with open(tmp_path / "exception_log.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1


def test_log_appends_rows_for_different_run_ids(tmp_path):
    """Different run IDs produce separate rows without overwriting existing ones."""
    from src.output.exception_logger import ExceptionLogger

    el = ExceptionLogger(log_dir=str(tmp_path))
    el.log(_make_run_result("run-001", [_make_triage_result("exc-001")]))
    el.log(_make_run_result("run-002", [_make_triage_result("exc-001")]))

    with open(tmp_path / "exception_log.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["run_id"] == "run-001"
    assert rows[1]["run_id"] == "run-002"


def test_log_creates_directory_if_missing(tmp_path):
    """log() creates the log_dir if it does not exist."""
    from src.output.exception_logger import ExceptionLogger

    nested = tmp_path / "deep" / "logs"
    el = ExceptionLogger(log_dir=str(nested))
    el.log(_make_run_result("run-001", [_make_triage_result()]))

    assert (nested / "exception_log.csv").exists()
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_exception_logger.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.output.exception_logger'`

- [ ] **Step 3: Implement `src/output/exception_logger.py`**

```python
"""Exception logger for Layer 4 (Task 6.4).

Appends a flat CSV record for every triage result. Idempotent on
(run_id, exception_id): re-running with the same run_id never duplicates rows.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Set, Tuple

from loguru import logger

from src.models import TriageResult, TriageRunResult

_CSV_FIELDNAMES = [
    "run_id", "run_date", "exception_id", "item_id", "store_id",
    "exception_type", "exception_date", "days_of_supply", "promo_active",
    "store_tier", "vendor_fill_rate_90d", "dc_inventory_days",
    "est_lost_sales_value", "promo_margin_at_risk",
    "enrichment_confidence", "missing_data_count",
    "ai_priority", "ai_confidence", "ai_root_cause", "ai_recommended_action",
    "ai_financial_impact", "ai_planner_brief",
    "pattern_id", "escalated_from", "phantom_flag", "run_timestamp",
]


class ExceptionLogger:
    """Appends triage results to a persistent CSV log for backtesting."""

    def __init__(self, log_dir: str = "output/logs") -> None:
        self._log_dir = Path(log_dir)
        self._log_path = self._log_dir / "exception_log.csv"

    def log(self, run_result: TriageRunResult) -> int:
        """Append all triage results from run_result to the exception log.

        Args:
            run_result: Complete output of one triage pipeline run.

        Returns:
            Number of new rows written (0 if all were already present).
        """
        self._log_dir.mkdir(parents=True, exist_ok=True)
        write_header = not self._log_path.exists()

        existing_keys: Set[Tuple[str, str]] = set()
        if not write_header:
            with self._log_path.open("r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing_keys.add((row["run_id"], row["exception_id"]))

        rows_written = 0
        with self._log_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
            if write_header:
                writer.writeheader()
            for tr in run_result.triage_results:
                key = (run_result.run_id, tr.exception_id)
                if key in existing_keys:
                    continue
                writer.writerow(_to_csv_row(tr, run_result))
                rows_written += 1

        logger.info(
            f"ExceptionLogger: wrote {rows_written} new rows to {self._log_path} "
            f"(run_id={run_result.run_id})."
        )
        return rows_written


def _to_csv_row(tr: TriageResult, run_result: TriageRunResult) -> dict:
    """Build a flat CSV row from a TriageResult and its run context."""
    return {
        "run_id": run_result.run_id,
        "run_date": run_result.run_date.isoformat(),
        "exception_id": tr.exception_id,
        "item_id": tr.item_id or "",
        "store_id": tr.store_id or "",
        "exception_type": tr.exception_type or "",
        "exception_date": "",
        "days_of_supply": tr.days_of_supply if tr.days_of_supply is not None else "",
        "promo_active": tr.promo_active if tr.promo_active is not None else "",
        "store_tier": tr.store_tier if tr.store_tier is not None else "",
        "vendor_fill_rate_90d": (
            tr.vendor_fill_rate_90d if tr.vendor_fill_rate_90d is not None else ""
        ),
        "dc_inventory_days": (
            tr.dc_inventory_days if tr.dc_inventory_days is not None else ""
        ),
        "est_lost_sales_value": (
            tr.est_lost_sales_value if tr.est_lost_sales_value is not None else ""
        ),
        "promo_margin_at_risk": (
            tr.promo_margin_at_risk if tr.promo_margin_at_risk is not None else ""
        ),
        "enrichment_confidence": tr.confidence.value,
        "missing_data_count": len(tr.missing_data_flags),
        "ai_priority": tr.priority.value,
        "ai_confidence": tr.confidence.value,
        "ai_root_cause": tr.root_cause,
        "ai_recommended_action": tr.recommended_action,
        "ai_financial_impact": tr.financial_impact_statement,
        "ai_planner_brief": tr.planner_brief,
        "pattern_id": tr.pattern_id or "",
        "escalated_from": tr.escalated_from or "",
        "phantom_flag": tr.phantom_flag,
        "run_timestamp": run_result.run_timestamp.isoformat(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_exception_logger.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/output/exception_logger.py tests/test_exception_logger.py
git commit -m "feat: add ExceptionLogger for Layer 4 (Task 6.4)"
```

---

### Task 4: Alert Dispatcher (`src/output/alert_dispatcher.py`)

**Files:**
- Create: `src/output/alert_dispatcher.py`
- Create: `tests/test_alert_dispatcher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alert_dispatcher.py`:

```python
"""Tests for AlertDispatcher (Task 6.2)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)
from src.utils.config_loader import AlertChannelConfig, AlertingConfig


def _make_triage_result(exception_id: str, priority: Priority) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Low stock",
        recommended_action="Expedite order",
        financial_impact_statement="$10,000 at risk",
        planner_brief="Urgent action needed.",
    )


def _make_run_result(triage_results) -> TriageRunResult:
    return TriageRunResult(
        run_id="run-001",
        run_date=date(2026, 4, 4),
        triage_results=triage_results,
        pattern_report=MacroPatternReport(),
        statistics=RunStatistics(),
        run_timestamp=datetime(2026, 4, 4, 8, 0, 0),
    )


def _slack_channel(enabled: bool = True) -> AlertChannelConfig:
    return AlertChannelConfig(
        type="slack", enabled=enabled, webhook_url="http://slack.example.com/hook"
    )


def test_dispatch_returns_zero_when_no_alerts_flag():
    """dispatch() returns 0 and sends nothing when no_alerts=True."""
    from src.output.alert_dispatcher import AlertDispatcher

    config = AlertingConfig(channels=[_slack_channel()])
    dispatcher = AlertDispatcher(config)
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.CRITICAL)])

    with patch("src.output.alert_dispatcher._send_slack") as mock_send:
        result = dispatcher.dispatch(run_result, no_alerts=True)

    assert result == 0
    mock_send.assert_not_called()


def test_dispatch_fires_only_for_critical_and_high():
    """dispatch() sends alerts for CRITICAL and HIGH, skips MEDIUM and LOW."""
    from src.output.alert_dispatcher import AlertDispatcher

    config = AlertingConfig(channels=[_slack_channel()])
    dispatcher = AlertDispatcher(config)
    run_result = _make_run_result([
        _make_triage_result("exc-001", Priority.CRITICAL),
        _make_triage_result("exc-002", Priority.HIGH),
        _make_triage_result("exc-003", Priority.MEDIUM),
        _make_triage_result("exc-004", Priority.LOW),
    ])

    with patch("src.output.alert_dispatcher._send_slack") as mock_send:
        with patch("threading.Timer"):
            result = dispatcher.dispatch(run_result)

    assert result == 2
    assert mock_send.call_count == 2


def test_dispatch_skips_disabled_channels():
    """dispatch() does not call send functions for disabled channels."""
    from src.output.alert_dispatcher import AlertDispatcher

    config = AlertingConfig(channels=[_slack_channel(enabled=False)])
    dispatcher = AlertDispatcher(config)
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.CRITICAL)])

    with patch("src.output.alert_dispatcher._send_slack") as mock_send:
        with patch("threading.Timer"):
            dispatcher.dispatch(run_result)

    mock_send.assert_not_called()


def test_dispatch_routes_to_correct_channel_functions():
    """dispatch() calls the correct send function for each channel type."""
    from src.output.alert_dispatcher import AlertDispatcher

    channels = [
        AlertChannelConfig(
            type="email", enabled=True,
            smtp_host="smtp.example.com", to_addresses=["x@y.com"]
        ),
        AlertChannelConfig(
            type="slack", enabled=True, webhook_url="http://slack.example.com"
        ),
        AlertChannelConfig(
            type="teams", enabled=True, webhook_url="http://teams.example.com"
        ),
        AlertChannelConfig(
            type="webhook", enabled=True, webhook_url="http://hook.example.com"
        ),
    ]
    config = AlertingConfig(channels=channels)
    dispatcher = AlertDispatcher(config)
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.HIGH)])

    with patch("src.output.alert_dispatcher._send_email") as me, \
         patch("src.output.alert_dispatcher._send_slack") as ms, \
         patch("src.output.alert_dispatcher._send_teams") as mt, \
         patch("src.output.alert_dispatcher._send_webhook") as mw:
        dispatcher.dispatch(run_result)

    me.assert_called_once()
    ms.assert_called_once()
    mt.assert_called_once()
    mw.assert_called_once()


def test_dispatch_schedules_sla_timer_for_each_critical():
    """A threading.Timer is started for each CRITICAL result when escalation contact is set."""
    from src.output.alert_dispatcher import AlertDispatcher

    config = AlertingConfig(
        channels=[_slack_channel()],
        critical_sla_minutes=30,
        secondary_escalation_contact="oncall@example.com",
    )
    dispatcher = AlertDispatcher(config)
    run_result = _make_run_result([
        _make_triage_result("exc-001", Priority.CRITICAL),
        _make_triage_result("exc-002", Priority.CRITICAL),
        _make_triage_result("exc-003", Priority.HIGH),
    ])

    with patch("src.output.alert_dispatcher._send_slack"):
        with patch("src.output.alert_dispatcher.threading.Timer") as MockTimer:
            mock_timer_instance = MagicMock()
            MockTimer.return_value = mock_timer_instance
            dispatcher.dispatch(run_result)

    assert MockTimer.call_count == 2  # only CRITICAL, not HIGH
    assert mock_timer_instance.start.call_count == 2


def test_format_alert_includes_low_confidence_note():
    """_format_alert appends low-confidence warning when confidence is LOW."""
    from src.output.alert_dispatcher import _format_alert

    tr = _make_triage_result("exc-001", Priority.CRITICAL)
    tr.confidence = EnrichmentConfidence.LOW
    tr.missing_data_flags = ["vendor_fill_rate_90d", "dc_inventory_days"]

    content = _format_alert(tr, "run-001")

    assert "LOW CONFIDENCE" in content
    assert "vendor_fill_rate_90d" in content
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_alert_dispatcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.output.alert_dispatcher'`

- [ ] **Step 3: Implement `src/output/alert_dispatcher.py`**

```python
"""Alert dispatcher for Layer 4 (Task 6.2).

Dispatches CRITICAL and HIGH triage alerts across configured channels.
CRITICAL alerts trigger a background SLA escalation timer.

Supported channel types (configured in alerting.channels):
  - "email"   — SMTP via smtplib
  - "slack"   — POST to Slack webhook URL
  - "teams"   — POST to Microsoft Teams webhook URL
  - "webhook" — POST to generic HTTP webhook URL

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import smtplib
import threading
from datetime import datetime
from email.mime.text import MIMEText
from typing import Set

import httpx
from loguru import logger

from src.models import EnrichmentConfidence, Priority, TriageResult, TriageRunResult
from src.utils.config_loader import AlertChannelConfig, AlertingConfig

_ALERT_PRIORITIES: Set[Priority] = {Priority.CRITICAL, Priority.HIGH}

_ALERT_TEMPLATE = (
    "🚨 REPLENISHMENT TRIAGE ALERT — {priority}\n\n"
    "Item: {item_name} | Store: {store_name} (Tier {store_tier})\n"
    "Exception: {exception_type} | Days of Supply: {days_of_supply}\n"
    "Financial Exposure: ${est_lost_sales_value:,.0f} lost sales"
    " | ${promo_margin_at_risk:,.0f} promo margin at risk\n\n"
    "ACTION REQUIRED: {recommended_action}\n\n"
    "{planner_brief}\n\n"
    "Root Cause: {root_cause}\n"
    "Confidence: {confidence}\n"
    "{low_confidence_note}"
    "Run ID: {run_id} | Generated: {timestamp}"
)


def _format_alert(tr: TriageResult, run_id: str, escalation_note: str = "") -> str:
    """Format the standard alert message for a single TriageResult."""
    low_conf_note = ""
    if tr.confidence == EnrichmentConfidence.LOW:
        low_conf_note = (
            f"⚠️ LOW CONFIDENCE — verify {tr.missing_data_flags} before acting.\n"
        )
    days = f"{tr.days_of_supply:.1f}" if tr.days_of_supply is not None else "N/A"
    content = _ALERT_TEMPLATE.format(
        priority=tr.priority.value,
        item_name=tr.item_name or "Unknown",
        store_name=tr.store_name or "Unknown",
        store_tier=tr.store_tier or "?",
        exception_type=tr.exception_type or "Unknown",
        days_of_supply=days,
        est_lost_sales_value=tr.est_lost_sales_value or 0.0,
        promo_margin_at_risk=tr.promo_margin_at_risk or 0.0,
        recommended_action=tr.recommended_action,
        planner_brief=tr.planner_brief,
        root_cause=tr.root_cause,
        confidence=tr.confidence.value,
        low_confidence_note=low_conf_note,
        run_id=run_id,
        timestamp=datetime.now().isoformat(),
    )
    if escalation_note:
        content += f"\n\n{escalation_note}"
    return content


class AlertDispatcher:
    """Dispatches CRITICAL and HIGH alerts across configured channels."""

    def __init__(self, config: AlertingConfig) -> None:
        self._config = config

    def dispatch(self, run_result: TriageRunResult, no_alerts: bool = False) -> int:
        """Dispatch alerts for CRITICAL and HIGH triage results.

        Args:
            run_result: Complete output of one triage pipeline run.
            no_alerts: If True, skip all dispatch.

        Returns:
            Number of alerts dispatched (0 if no_alerts=True).
        """
        if no_alerts:
            logger.info("AlertDispatcher: no_alerts=True — skipping all dispatch.")
            return 0

        alert_results = [
            tr for tr in run_result.triage_results if tr.priority in _ALERT_PRIORITIES
        ]

        count = 0
        for tr in alert_results:
            content = _format_alert(tr, run_result.run_id)
            self._send_to_all_channels(content)
            count += 1
            if tr.priority == Priority.CRITICAL:
                self._schedule_sla_escalation(tr, run_result.run_id)

        logger.info(f"AlertDispatcher: dispatched {count} alerts.")
        return count

    def _send_to_all_channels(self, content: str) -> None:
        """Send alert content to every enabled channel."""
        for channel in self._config.channels:
            if not channel.enabled:
                continue
            try:
                if channel.type == "email":
                    _send_email(content, channel)
                elif channel.type == "slack":
                    _send_slack(content, channel)
                elif channel.type == "teams":
                    _send_teams(content, channel)
                elif channel.type == "webhook":
                    _send_webhook(content, channel)
                else:
                    logger.warning(
                        f"AlertDispatcher: unknown channel type {channel.type!r}."
                    )
            except Exception as exc:
                logger.error(
                    f"AlertDispatcher: channel {channel.type!r} failed: {exc}. "
                    "Continuing to next channel."
                )

    def _schedule_sla_escalation(self, tr: TriageResult, run_id: str) -> None:
        """Start a background timer to fire a secondary alert after the SLA window."""
        if not self._config.secondary_escalation_contact:
            return
        sla_seconds = self._config.critical_sla_minutes * 60
        escalation_note = (
            f"ESCALATION: Unacknowledged after "
            f"{self._config.critical_sla_minutes} minutes."
        )
        content = _format_alert(tr, run_id, escalation_note=escalation_note)
        contact = self._config.secondary_escalation_contact

        def _fire() -> None:
            logger.warning(
                f"AlertDispatcher: SLA breach for {tr.exception_id} — "
                f"escalating to {contact}."
            )
            try:
                _send_email(
                    content,
                    AlertChannelConfig(
                        type="email", enabled=True, to_addresses=[contact]
                    ),
                )
            except Exception as exc:
                logger.error(f"AlertDispatcher: escalation email failed: {exc}.")

        timer = threading.Timer(sla_seconds, _fire)
        timer.daemon = True
        timer.start()
        logger.debug(
            f"AlertDispatcher: SLA timer ({self._config.critical_sla_minutes}m) "
            f"started for {tr.exception_id}."
        )


# --- Channel send functions ---

def _send_email(content: str, channel: AlertChannelConfig) -> None:
    if not channel.smtp_host or not channel.to_addresses:
        logger.warning(
            "AlertDispatcher: email channel missing smtp_host or to_addresses."
        )
        return
    msg = MIMEText(content)
    msg["Subject"] = "🚨 Replenishment Triage Alert"
    msg["From"] = channel.from_address or "triage-agent@noreply.internal"
    msg["To"] = ", ".join(channel.to_addresses)
    with smtplib.SMTP(channel.smtp_host, channel.smtp_port or 25) as smtp:
        smtp.sendmail(msg["From"], channel.to_addresses, msg.as_string())


def _send_slack(content: str, channel: AlertChannelConfig) -> None:
    if not channel.webhook_url:
        logger.warning("AlertDispatcher: Slack channel missing webhook_url.")
        return
    httpx.post(channel.webhook_url, json={"text": content}, timeout=10.0)


def _send_teams(content: str, channel: AlertChannelConfig) -> None:
    if not channel.webhook_url:
        logger.warning("AlertDispatcher: Teams channel missing webhook_url.")
        return
    httpx.post(
        channel.webhook_url,
        json={"@type": "MessageCard", "text": content},
        timeout=10.0,
    )


def _send_webhook(content: str, channel: AlertChannelConfig) -> None:
    if not channel.webhook_url:
        logger.warning("AlertDispatcher: generic webhook channel missing webhook_url.")
        return
    httpx.post(channel.webhook_url, json={"alert": content}, timeout=10.0)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_alert_dispatcher.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/output/alert_dispatcher.py tests/test_alert_dispatcher.py
git commit -m "feat: add AlertDispatcher for Layer 4 (Task 6.2)"
```

---

### Task 5: Morning Briefing Generator (`src/output/briefing_generator.py`)

**Files:**
- Create: `src/output/briefing_generator.py`
- Create: `tests/test_briefing_generator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_briefing_generator.py`:

```python
"""Tests for BriefingGenerator (Task 6.3)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    EnrichmentConfidence,
    MacroPatternReport,
    Priority,
    RunStatistics,
    TriageResult,
    TriageRunResult,
)
from src.utils.config_loader import AppConfig


def _make_triage_result(
    exception_id: str,
    priority: Priority,
    est_lost_sales_value: float = 1000.0,
) -> TriageResult:
    return TriageResult(
        exception_id=exception_id,
        priority=priority,
        confidence=EnrichmentConfidence.HIGH,
        root_cause="Vendor delay",
        recommended_action="Expedite order",
        financial_impact_statement="$1,000 at risk",
        planner_brief="Action needed.",
        item_name="Widget A",
        store_name="Store 001",
        est_lost_sales_value=est_lost_sales_value,
    )


def _make_run_result(triage_results) -> TriageRunResult:
    stats = RunStatistics(
        total_exceptions=len(triage_results),
        critical_count=sum(1 for t in triage_results if t.priority == Priority.CRITICAL),
        high_count=sum(1 for t in triage_results if t.priority == Priority.HIGH),
        medium_count=sum(1 for t in triage_results if t.priority == Priority.MEDIUM),
        low_count=sum(1 for t in triage_results if t.priority == Priority.LOW),
    )
    return TriageRunResult(
        run_id="run-001",
        run_date=date(2026, 4, 4),
        triage_results=triage_results,
        pattern_report=MacroPatternReport(),
        statistics=stats,
        run_timestamp=datetime(2026, 4, 4, 8, 0, 0),
    )


@patch("src.output.briefing_generator.get_provider")
def test_generate_writes_markdown_file(mock_get_provider, tmp_path):
    """generate() writes a .md file to the briefings directory."""
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MagicMock(text="Executive summary text.")
    mock_get_provider.return_value = mock_provider

    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "briefings")
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.CRITICAL)])

    from src.output.briefing_generator import BriefingGenerator
    path = BriefingGenerator(config).generate(run_result)

    assert path.exists()
    assert path.suffix == ".md"
    assert "Morning Briefing" in path.read_text()


@patch("src.output.briefing_generator.get_provider")
def test_generate_calls_llm_exactly_once_for_executive_summary(
    mock_get_provider, tmp_path
):
    """generate() calls the LLM exactly once — for the executive summary."""
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MagicMock(text="Summary.")
    mock_get_provider.return_value = mock_provider

    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "briefings")
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.CRITICAL)])

    from src.output.briefing_generator import BriefingGenerator
    BriefingGenerator(config).generate(run_result)

    mock_provider.complete.assert_called_once()


@patch("src.output.briefing_generator.get_provider")
def test_generate_does_not_call_llm_when_no_critical(mock_get_provider, tmp_path):
    """generate() uses a fallback summary and skips the LLM call when no CRITICAL results."""
    mock_provider = MagicMock()
    mock_get_provider.return_value = mock_provider

    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "briefings")
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.LOW)])

    from src.output.briefing_generator import BriefingGenerator
    BriefingGenerator(config).generate(run_result)

    mock_provider.complete.assert_not_called()


@patch("src.output.briefing_generator.get_provider")
def test_generate_financial_totals_match_sum_of_values(mock_get_provider, tmp_path):
    """Financial totals in the briefing match the sum of individual exception values."""
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MagicMock(text="Summary.")
    mock_get_provider.return_value = mock_provider

    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "briefings")
    results = [
        _make_triage_result("exc-001", Priority.CRITICAL, est_lost_sales_value=1000.0),
        _make_triage_result("exc-002", Priority.HIGH, est_lost_sales_value=500.0),
    ]
    run_result = _make_run_result(results)

    from src.output.briefing_generator import BriefingGenerator
    path = BriefingGenerator(config).generate(run_result)

    content = path.read_text()
    assert "1,500" in content  # TOTAL row: $1,000 + $500


@patch("src.output.briefing_generator.get_provider")
def test_generate_briefing_contains_run_statistics(mock_get_provider, tmp_path):
    """Briefing contains the run statistics section."""
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MagicMock(text="Summary.")
    mock_get_provider.return_value = mock_provider

    config = AppConfig()
    config.output.briefing_dir = str(tmp_path / "briefings")
    run_result = _make_run_result([_make_triage_result("exc-001", Priority.HIGH)])

    from src.output.briefing_generator import BriefingGenerator
    path = BriefingGenerator(config).generate(run_result)

    content = path.read_text()
    assert "Run Statistics" in content
    assert "Total exceptions processed" in content
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_briefing_generator.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.output.briefing_generator'`

- [ ] **Step 3: Implement `src/output/briefing_generator.py`**

```python
"""Morning briefing generator for Layer 4 (Task 6.3).

Generates a markdown briefing document. The LLM is called exactly once to
generate the executive summary section — all other content is templated.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from loguru import logger

from src.agent.llm_provider import get_provider
from src.models import (
    MacroPatternReport,
    Priority,
    TriageResult,
    TriageRunResult,
)
from src.utils.config_loader import AppConfig

_EXEC_SUMMARY_SYSTEM = (
    "You are a supply chain briefing writer. "
    "Write a concise executive summary for a supply chain director. "
    "Be direct, specific, and avoid jargon."
)


class BriefingGenerator:
    """Generates the daily markdown briefing document."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._provider = get_provider(config.agent)
        self._briefing_dir = Path(config.output.briefing_dir)

    def generate(self, run_result: TriageRunResult) -> Path:
        """Generate and save the morning briefing.

        Args:
            run_result: Complete output of one triage pipeline run.

        Returns:
            Path to the written briefing file.
        """
        self._briefing_dir.mkdir(parents=True, exist_ok=True)
        output_path = (
            self._briefing_dir / f"briefing_{run_result.run_date.isoformat()}.md"
        )

        critical_results = sorted(
            [tr for tr in run_result.triage_results if tr.priority == Priority.CRITICAL],
            key=lambda t: t.est_lost_sales_value or 0.0,
            reverse=True,
        )

        exec_summary = self._generate_exec_summary(
            critical_results, run_result.pattern_report
        )
        content = _render_briefing(
            run_result=run_result,
            critical_results=critical_results,
            exec_summary=exec_summary,
            max_exceptions=self._config.output.max_exceptions_in_briefing,
        )

        output_path.write_text(content, encoding="utf-8")
        logger.info(f"BriefingGenerator: briefing saved to {output_path}.")
        return output_path

    def _generate_exec_summary(
        self,
        critical_results: List[TriageResult],
        pattern_report: MacroPatternReport,
    ) -> str:
        if not critical_results:
            return (
                "No CRITICAL exceptions today. "
                "All priority queues are within normal parameters."
            )
        prompt = _build_exec_summary_prompt(critical_results, pattern_report)
        try:
            response = self._provider.complete(_EXEC_SUMMARY_SYSTEM, prompt)
            return response.text.strip()
        except Exception as exc:
            logger.warning(
                f"BriefingGenerator: LLM call failed: {exc}. Using fallback summary."
            )
            return (
                f"Today's run flagged {len(critical_results)} CRITICAL exception(s). "
                "Manual review recommended."
            )


def _build_exec_summary_prompt(
    top_critical: List[TriageResult],
    pattern_report: MacroPatternReport,
) -> str:
    lines = [
        "Write a 3-4 sentence executive summary of today's most critical supply chain situation.",
        "Mention the highest-risk exception by name, the financial exposure,",
        "and the most important systemic pattern if one exists.",
        "Be direct and specific. No jargon.",
        "",
        "Top CRITICAL exceptions:",
    ]
    for tr in top_critical[:5]:
        lines.append(
            f"  - {tr.item_name or 'Unknown item'} at {tr.store_name or 'unknown store'}: "
            f"${tr.est_lost_sales_value or 0:,.0f} lost sales risk. "
            f"Root cause: {tr.root_cause}"
        )
    if pattern_report.patterns:
        p = pattern_report.patterns[0]
        lines.append(
            f"\nTop pattern: {p.pattern_type.value} / {p.group_key} — {p.description}"
        )
    return "\n".join(lines)


def _priority_icon(priority: Priority) -> str:
    return {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢",
    }.get(priority.value, "⚪")


def _render_briefing(
    run_result: TriageRunResult,
    critical_results: List[TriageResult],
    exec_summary: str,
    max_exceptions: int,
) -> str:
    stats = run_result.statistics
    pr = run_result.pattern_report
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _total_value(priority: Priority) -> float:
        return sum(
            tr.est_lost_sales_value or 0.0
            for tr in run_result.triage_results
            if tr.priority == priority
        )

    total_value = sum(
        tr.est_lost_sales_value or 0.0 for tr in run_result.triage_results
    )

    lines = [
        "# Replenishment Exception Triage — Morning Briefing",
        f"**Date:** {run_result.run_date} | **Run ID:** {run_result.run_id} | **Generated:** {now}",
        "",
        "---",
        "",
        "## Today at a Glance",
        "| Priority | Count | Total Financial Exposure |",
        "|---|---|---|",
        f"| 🔴 CRITICAL | {stats.critical_count} | ${_total_value(Priority.CRITICAL):,.0f} |",
        f"| 🟠 HIGH | {stats.high_count} | ${_total_value(Priority.HIGH):,.0f} |",
        f"| 🟡 MEDIUM | {stats.medium_count} | ${_total_value(Priority.MEDIUM):,.0f} |",
        f"| 🟢 LOW | {stats.low_count} | ${_total_value(Priority.LOW):,.0f} |",
        f"| **TOTAL** | **{stats.total_exceptions}** | **${total_value:,.0f}** |",
        "",
        "---",
        "",
        "## Systemic Patterns Detected",
    ]

    if pr.patterns:
        for p in pr.patterns:
            lines.append(
                f"- **{p.pattern_type.value}** / {p.group_key}: "
                f"{p.affected_count} exceptions — {p.description} "
                f"({p.escalation_count} escalations)"
            )
    else:
        lines.append("No systemic patterns detected.")

    lines += [
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        exec_summary,
        "",
        "---",
        "",
        f"## Top {min(len(critical_results), max_exceptions)} Critical Exceptions",
        "",
    ]

    for i, tr in enumerate(critical_results[:max_exceptions], 1):
        days_str = (
            f"{tr.days_of_supply:.1f}" if tr.days_of_supply is not None else "N/A"
        )
        lines += [
            f"### {i}. {tr.item_name or 'Unknown'} — {tr.store_name or 'Unknown'}",
            f"**Priority:** 🔴 CRITICAL | **Confidence:** {tr.confidence.value}  ",
            f"**Exception:** {tr.exception_type or 'Unknown'} | "
            f"**Days of Supply:** {days_str}  ",
            f"**Financial Exposure:** ${tr.est_lost_sales_value or 0:,.0f} lost sales | "
            f"${tr.promo_margin_at_risk or 0:,.0f} promo margin  ",
            f"**Root Cause:** {tr.root_cause}  ",
            f"**Action Required:** {tr.recommended_action}  ",
            "",
            f"> {tr.planner_brief}",
            "",
        ]
        if tr.missing_data_flags:
            lines.append(f"⚠️ Missing data: {', '.join(tr.missing_data_flags)}  ")
        if tr.compounding_risks:
            lines.append(
                f"⚠️ Compounding risks: {', '.join(tr.compounding_risks)}  "
            )
        lines += ["", "---", ""]

    lines += [
        "## Full Exception Queue",
        "",
        "| # | Priority | Item | Store | Exception | Days Supply | Financial Exposure | Action |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, tr in enumerate(run_result.triage_results, 1):
        icon = _priority_icon(tr.priority)
        days = f"{tr.days_of_supply:.1f}" if tr.days_of_supply is not None else "N/A"
        lines.append(
            f"| {i} | {icon} {tr.priority.value} | {tr.item_name or '—'} | "
            f"{tr.store_name or '—'} | {tr.exception_type or '—'} | {days} | "
            f"${tr.est_lost_sales_value or 0:,.0f} | {tr.recommended_action} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Run Statistics",
        f"- Total exceptions processed: {stats.total_exceptions}",
        f"- Batches: {stats.batches_completed} completed, {stats.batches_failed} failed",
        f"- Pattern escalations applied: {stats.pattern_escalations}",
        f"- Phantom inventory flags: {stats.phantom_flags}",
        f"- Pipeline completion time: {stats.pipeline_duration_seconds:.1f}s",
        "",
    ]

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_briefing_generator.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/output/briefing_generator.py tests/test_briefing_generator.py
git commit -m "feat: add BriefingGenerator for Layer 4 (Task 6.3)"
```

---

### Task 6: Main Orchestrator + CLI (`src/main.py` + `scripts/run_triage.py`)

**Files:**
- Create: `src/main.py`
- Create: `scripts/run_triage.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:

```python
"""Tests for run_triage_pipeline() (Task 7.1)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    MacroPatternReport,
    RunStatistics,
    TriageRunResult,
)


def _make_run_result() -> TriageRunResult:
    from datetime import datetime
    return TriageRunResult(
        run_id="run-001",
        run_date=date(2026, 4, 4),
        triage_results=[],
        pattern_report=MacroPatternReport(),
        statistics=RunStatistics(),
        run_timestamp=datetime(2026, 4, 4, 8, 0, 0),
    )


@patch("src.main.ExceptionLogger")
@patch("src.main.BriefingGenerator")
@patch("src.main.AlertDispatcher")
@patch("src.main.PriorityRouter")
@patch("src.main.TriageAgent")
@patch("src.main.EnrichmentEngine")
@patch("src.main.DataLoader")
@patch("src.main.Normalizer")
@patch("src.main.CSVAdapter")
@patch("src.main.load_config")
def test_run_triage_pipeline_returns_triage_run_result(
    mock_load_config,
    MockCSVAdapter,
    MockNormalizer,
    MockDataLoader,
    MockEnrichmentEngine,
    MockTriageAgent,
    MockPriorityRouter,
    MockAlertDispatcher,
    MockBriefingGenerator,
    MockExceptionLogger,
):
    """run_triage_pipeline() returns a TriageRunResult."""
    mock_load_config.return_value = MagicMock()
    MockCSVAdapter.return_value.fetch.return_value = []
    MockNormalizer.return_value.normalize.return_value = ([], 0)
    MockDataLoader.return_value.load.return_value = MagicMock()
    MockEnrichmentEngine.return_value.enrich.return_value = []
    MockTriageAgent.return_value.run.return_value = _make_run_result()
    MockPriorityRouter.return_value.route.return_value = {}
    MockBriefingGenerator.return_value.generate.return_value = MagicMock()
    MockExceptionLogger.return_value.log.return_value = 0

    from src.main import run_triage_pipeline
    result = run_triage_pipeline()

    assert isinstance(result, TriageRunResult)


@patch("src.main.ExceptionLogger")
@patch("src.main.BriefingGenerator")
@patch("src.main.AlertDispatcher")
@patch("src.main.PriorityRouter")
@patch("src.main.TriageAgent")
@patch("src.main.EnrichmentEngine")
@patch("src.main.DataLoader")
@patch("src.main.Normalizer")
@patch("src.main.CSVAdapter")
@patch("src.main.load_config")
def test_run_triage_pipeline_dry_run_skips_ai_and_output(
    mock_load_config,
    MockCSVAdapter,
    MockNormalizer,
    MockDataLoader,
    MockEnrichmentEngine,
    MockTriageAgent,
    MockPriorityRouter,
    MockAlertDispatcher,
    MockBriefingGenerator,
    MockExceptionLogger,
):
    """dry_run=True skips the TriageAgent, router, alerts, briefing, and logger."""
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config
    MockCSVAdapter.return_value.fetch.return_value = []
    MockNormalizer.return_value.normalize.return_value = ([], 0)
    MockDataLoader.return_value.load.return_value = MagicMock()
    MockEnrichmentEngine.return_value.enrich.return_value = []

    from src.main import run_triage_pipeline
    result = run_triage_pipeline(dry_run=True)

    MockTriageAgent.return_value.run.assert_not_called()
    MockPriorityRouter.return_value.route.assert_not_called()
    MockBriefingGenerator.return_value.generate.assert_not_called()
    MockExceptionLogger.return_value.log.assert_not_called()


@patch("src.main.ExceptionLogger")
@patch("src.main.BriefingGenerator")
@patch("src.main.AlertDispatcher")
@patch("src.main.PriorityRouter")
@patch("src.main.TriageAgent")
@patch("src.main.EnrichmentEngine")
@patch("src.main.DataLoader")
@patch("src.main.Normalizer")
@patch("src.main.CSVAdapter")
@patch("src.main.load_config")
def test_run_triage_pipeline_no_alerts_passes_flag(
    mock_load_config,
    MockCSVAdapter,
    MockNormalizer,
    MockDataLoader,
    MockEnrichmentEngine,
    MockTriageAgent,
    MockPriorityRouter,
    MockAlertDispatcher,
    MockBriefingGenerator,
    MockExceptionLogger,
):
    """no_alerts=True is passed through to AlertDispatcher.dispatch()."""
    mock_load_config.return_value = MagicMock()
    MockCSVAdapter.return_value.fetch.return_value = []
    MockNormalizer.return_value.normalize.return_value = ([], 0)
    MockDataLoader.return_value.load.return_value = MagicMock()
    MockEnrichmentEngine.return_value.enrich.return_value = []
    MockTriageAgent.return_value.run.return_value = _make_run_result()
    MockPriorityRouter.return_value.route.return_value = {}
    MockBriefingGenerator.return_value.generate.return_value = MagicMock()
    MockExceptionLogger.return_value.log.return_value = 0

    from src.main import run_triage_pipeline
    run_triage_pipeline(no_alerts=True)

    MockAlertDispatcher.return_value.dispatch.assert_called_once()
    _, kwargs = MockAlertDispatcher.return_value.dispatch.call_args
    assert kwargs.get("no_alerts") is True or (
        len(MockAlertDispatcher.return_value.dispatch.call_args.args) > 1
        and MockAlertDispatcher.return_value.dispatch.call_args.args[1] is True
    )
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.main'`

- [ ] **Step 3: Implement `src/main.py`**

```python
"""Main pipeline orchestrator (Task 7.1).

Entry point for the full replenishment exception triage pipeline.
Called directly or via scripts/run_triage.py.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from loguru import logger

from src.agent.triage_agent import TriageAgent
from src.enrichment.data_loader import DataLoader
from src.enrichment.engine import EnrichmentEngine
from src.ingestion.csv_adapter import CSVAdapter
from src.ingestion.normalizer import Normalizer
from src.models import TriageRunResult
from src.output.alert_dispatcher import AlertDispatcher
from src.output.briefing_generator import BriefingGenerator
from src.output.exception_logger import ExceptionLogger
from src.output.router import PriorityRouter
from src.utils.config_loader import load_config


def run_triage_pipeline(
    config_path: str = "config/config.yaml",
    run_date: Optional[str] = None,
    dry_run: bool = False,
    no_alerts: bool = False,
    use_sample: bool = False,
    verbose: bool = False,
) -> TriageRunResult:
    """Execute the full replenishment exception triage pipeline.

    Args:
        config_path: Path to the YAML config file.
        run_date: ISO date string (YYYY-MM-DD) for the run. Defaults to today.
        dry_run: If True, run Layer 1 and 2 only — skip AI triage and all output.
        no_alerts: If True, skip alert dispatch (still runs routing, briefing, logging).
        use_sample: If True, override the configured adapter to use the CSV sample file.
        verbose: If True, emit DEBUG-level log output.

    Returns:
        TriageRunResult (with empty triage_results if dry_run=True).
    """
    if verbose:
        import sys
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    config = load_config(config_path)

    reference_date: Optional[date] = None
    if run_date:
        reference_date = date.fromisoformat(run_date)

    # Override adapter to CSV sample if requested
    if use_sample:
        config.ingestion.adapter = "csv"

    # --- Layer 1: Ingestion ---
    logger.info("Pipeline: Layer 1 — ingesting exceptions.")
    adapter = CSVAdapter(
        file_path=config.ingestion.csv.path,
        delimiter=config.ingestion.csv.delimiter,
    )
    raw_records = adapter.fetch()
    normalizer = Normalizer(
        field_mapping=config.ingestion.field_mapping,
        quarantine_dir=config.output.log_dir,
    )
    canonical_exceptions, quarantine_count = normalizer.normalize(raw_records)
    logger.info(
        f"Pipeline: ingested {len(canonical_exceptions)} exceptions "
        f"({quarantine_count} quarantined)."
    )

    # --- Layer 2: Enrichment ---
    logger.info("Pipeline: Layer 2 — enriching exceptions.")
    loaded_data = DataLoader(config=config.enrichment).load()
    enriched_exceptions = EnrichmentEngine(
        loaded_data=loaded_data,
        reference_date=reference_date,
        null_threshold_low=config.enrichment.null_threshold_low_confidence,
        null_threshold_medium=config.enrichment.null_threshold_medium_confidence,
        promo_lift_factor=config.enrichment.promo_lift_factor,
    ).enrich(canonical_exceptions)
    logger.info(f"Pipeline: enriched {len(enriched_exceptions)} exceptions.")

    if dry_run:
        logger.info(
            "Pipeline: dry_run=True — skipping AI triage and output layers. "
            f"Enrichment summary: {len(enriched_exceptions)} exceptions ready."
        )
        from datetime import datetime
        from src.models import MacroPatternReport, RunStatistics
        return TriageRunResult(
            run_id="dry-run",
            run_date=reference_date or date.today(),
            triage_results=[],
            pattern_report=MacroPatternReport(),
            statistics=RunStatistics(total_exceptions=len(enriched_exceptions)),
            run_timestamp=datetime.now(),
        )

    if not enriched_exceptions:
        logger.warning("Pipeline: no enriched exceptions — skipping AI triage.")
        from datetime import datetime
        from src.models import MacroPatternReport, RunStatistics
        return TriageRunResult(
            run_id="empty-run",
            run_date=reference_date or date.today(),
            triage_results=[],
            pattern_report=MacroPatternReport(),
            statistics=RunStatistics(),
            run_timestamp=datetime.now(),
        )

    # --- Layer 3: AI Triage ---
    logger.info("Pipeline: Layer 3 — running AI triage agent.")
    run_result = TriageAgent(config).run(enriched_exceptions)

    # --- Layer 4: Output ---
    logger.info("Pipeline: Layer 4 — routing, alerting, briefing, logging.")
    PriorityRouter(log_dir=config.output.log_dir).route(run_result)
    AlertDispatcher(config.alerting).dispatch(run_result, no_alerts=no_alerts)
    BriefingGenerator(config).generate(run_result)
    ExceptionLogger(log_dir=config.output.log_dir).log(run_result)

    logger.info(
        f"Pipeline: complete. "
        f"CRITICAL={run_result.statistics.critical_count} "
        f"HIGH={run_result.statistics.high_count} "
        f"MEDIUM={run_result.statistics.medium_count} "
        f"LOW={run_result.statistics.low_count}"
    )
    return run_result
```

- [ ] **Step 4: Create `scripts/run_triage.py`**

```python
#!/usr/bin/env python
"""CLI entry point for the replenishment exception triage pipeline.

Usage:
    python scripts/run_triage.py [OPTIONS]

Options:
    --config PATH         Path to config YAML (default: config/config.yaml)
    --date DATE           Run date YYYY-MM-DD (default: today)
    --dry-run             Ingest + enrich only; skip AI and output layers
    --no-alerts           Skip alert dispatch
    --sample              Force CSV sample data regardless of adapter config
    --verbose             Detailed DEBUG logging to console
    --output-format FMT   markdown | json | both (overrides config; informational only)

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import argparse
import sys

from src.main import run_triage_pipeline


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Replenishment Exception Triage Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        metavar="PATH",
        help="Path to config YAML (default: config/config.yaml)",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="DATE",
        help="Run date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ingest + enrich only; skip AI triage and all output",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Skip alert dispatch",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Force CSV sample data regardless of adapter config",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    parser.add_argument(
        "--output-format",
        choices=["markdown", "json", "both"],
        default="markdown",
        metavar="FORMAT",
        help="Output format: markdown | json | both (default: markdown)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        result = run_triage_pipeline(
            config_path=args.config,
            run_date=args.date,
            dry_run=args.dry_run,
            no_alerts=args.no_alerts,
            use_sample=args.sample,
            verbose=args.verbose,
        )
        stats = result.statistics
        print(
            f"\nTriage run complete ({result.run_id})\n"
            f"  CRITICAL : {stats.critical_count}\n"
            f"  HIGH     : {stats.high_count}\n"
            f"  MEDIUM   : {stats.medium_count}\n"
            f"  LOW      : {stats.low_count}\n"
            f"  Patterns : {result.pattern_report.total_patterns}\n"
            f"  Duration : {stats.pipeline_duration_seconds:.1f}s"
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Run full suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass (232 existing + ~24 new = ~256 total).

- [ ] **Step 7: Smoke test the CLI**

```bash
python scripts/run_triage.py --sample --dry-run --verbose
```

Expected: prints enrichment summary and exits 0.

- [ ] **Step 8: Commit**

```bash
git add src/main.py scripts/run_triage.py tests/test_main.py
git commit -m "feat: add main orchestrator and run_triage.py CLI (Task 7.1)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Task 5.4 — TriageAgent orchestrator | Task 1 |
| Task 6.1 — Priority router (4 JSON files, sorted by value) | Task 2 |
| Task 6.2 — Alert dispatcher (CRITICAL/HIGH, 4 channels, SLA timer) | Task 4 |
| Task 6.3 — Morning briefing (LLM exec summary, templated rest) | Task 5 |
| Task 6.4 — Exception logger (CSV, idempotent on run_id+exception_id) | Task 3 |
| Task 7.1 — `run_triage_pipeline()` + CLI with all flags | Task 6 |

**Placeholder scan:** No TBDs, no "implement later", all code blocks contain working Python.

**Type consistency:**
- `TriageResult.missing_data_flags` used consistently across Tasks 4–6.
- `TriageResult.financial_impact_statement` used in Task 3 (`ai_financial_impact` column).
- `TriageResult.confidence: EnrichmentConfidence` used consistently — no `Confidence` references.
- `BatchProcessorResult` dataclass fields match what `batch_processor.py` actually declares.
