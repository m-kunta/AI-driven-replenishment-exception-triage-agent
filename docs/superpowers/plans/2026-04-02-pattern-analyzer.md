# Pattern Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/agent/pattern_analyzer.py` — Pass 2 of the triage pipeline that aggregates all batch triage results, identifies systemic vendor/region/category/DC patterns, calls the LLM once with a summary prompt, and escalates MEDIUM exceptions to HIGH for confirmed pattern members.

**Architecture:** `PatternAnalyzer` is initialized with `AppConfig`. Its single public method `analyze(triage_results, enriched_exceptions) -> MacroPatternReport` builds a macro summary prompt from aggregated counts, calls the LLM, parses the JSON pattern list, mutates matching `TriageResult` objects (sets `pattern_id`, `escalated_from`, upgrades `priority`), and returns a fully-populated `MacroPatternReport`.

**Tech Stack:** Python 3.9+, Pydantic v2, loguru, `src.agent.llm_provider.get_provider`, `src.models.{TriageResult, EnrichedExceptionSchema, MacroPatternReport, PatternDetail, PatternType, Priority}`, `src.utils.config_loader.AppConfig`.

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/agent/pattern_analyzer.py` | `PatternAnalyzer` class — aggregation, LLM call, escalation |
| Create | `tests/test_pattern_analyzer.py` | All unit tests (mocked LLM provider) |

**PatternAnalyzer internal decomposition:**
- `__init__(config: AppConfig)` — initializes LLM provider
- `analyze(triage_results, enriched_exceptions) -> MacroPatternReport` — public API
- `_build_aggregates(triage_results, enriched_exceptions) -> dict` — counts by vendor/region/category/dc (private)
- `_build_summary_prompt(aggregates) -> str` — formats the macro summary text (private, static-eligible)
- `_call_llm(summary_prompt) -> list[dict]` — sends prompt, parses JSON pattern list (private)
- `_apply_escalations(pattern_report, triage_results) -> int` — mutates triage_results in place, returns escalation count (private)

---

## Shared Test Helpers

Define at the top of `tests/test_pattern_analyzer.py`:

```python
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
```

---

## Task 1: PatternAnalyzer.__init__ + _build_aggregates

**Files:**
- Create: `src/agent/pattern_analyzer.py`
- Create: `tests/test_pattern_analyzer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pattern_analyzer.py` with the shared helpers above, then add:

```python
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
        """Exceptions with vendor_id=None should not appear in vendor aggregates."""
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [_make_triage_result("exc-001")]
        enriched = [_make_enriched_exception("exc-001", vendor_id=None)]
        aggs = analyzer._build_aggregates(triage, enriched)

        assert len(aggs["vendor"]) == 0

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_exception_ids_aligned_by_position(self, mock_get_provider):
        """triage_results and enriched_exceptions are matched by list position."""
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/MKunta/CODE/AI-driven-replenishment-exception-triage-agent
source .venv/bin/activate
pytest tests/test_pattern_analyzer.py::TestPatternAnalyzerInit tests/test_pattern_analyzer.py::TestBuildAggregates -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'src.agent.pattern_analyzer'`

- [ ] **Step 3: Create `src/agent/pattern_analyzer.py`**

```python
"""Pattern analyzer for the triage agent (Task 5.2).

Pass 2 of the triage pipeline — runs after all batch results are collected.
Aggregates by vendor/region/category, calls LLM once with macro summary,
confirms patterns, and escalates MEDIUM→HIGH for pattern members.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.agent.llm_provider import LLMProvider, get_provider
from src.models import (
    EnrichedExceptionSchema,
    MacroPatternReport,
    PatternDetail,
    PatternType,
    Priority,
    TriageResult,
)
from src.utils.config_loader import AppConfig

_PATTERN_SYSTEM_PROMPT = (
    "You are a supply chain pattern analyst. "
    "Given an aggregated summary of replenishment exceptions, identify systemic patterns "
    "that suggest a single root cause affecting multiple items, stores, or locations. "
    "Return a JSON array of pattern objects. Each object must have exactly these fields: "
    '{"pattern_type": "VENDOR|DC_LANE|CATEGORY|REGION|MACRO", '
    '"group_key": "the vendor/category/region/dc identifier", '
    '"count": <integer>, '
    '"description": "one sentence root cause"}. '
    "Return an empty array [] if no patterns meet the threshold. "
    "Do not wrap your response in markdown code fences."
)


class PatternAnalyzer:
    """Aggregates triage results across all batches and identifies systemic patterns.

    Responsibilities:
    - Build vendor/region/category/dc aggregates from all TriageResult + EnrichedExceptionSchema pairs
    - Construct a compact macro summary prompt and call the LLM once
    - Parse the JSON pattern list from the LLM response
    - Escalate MEDIUM TriageResults to HIGH for confirmed pattern members
    - Return a MacroPatternReport with all PatternDetail objects

    Usage:
        analyzer = PatternAnalyzer(config)
        report = analyzer.analyze(triage_results, enriched_exceptions)
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._provider: LLMProvider = get_provider(config.agent)

    def analyze(
        self,
        triage_results: List[TriageResult],
        enriched_exceptions: List[EnrichedExceptionSchema],
    ) -> MacroPatternReport:
        """Run Pass 2 pattern analysis across all triage results.

        Args:
            triage_results: All TriageResult objects from batch processing.
                Must be in the same order as enriched_exceptions.
            enriched_exceptions: All EnrichedExceptionSchema objects, positionally
                aligned with triage_results.

        Returns:
            MacroPatternReport with identified patterns. Mutates triage_results
            in place: sets pattern_id, escalated_from, and may upgrade priority.
        """
        if not triage_results:
            logger.info("PatternAnalyzer.analyze called with empty results — returning empty report.")
            return MacroPatternReport()

        aggregates = self._build_aggregates(triage_results, enriched_exceptions)
        threshold = self._config.agent.pattern_threshold

        # Filter aggregates to only groups meeting the threshold
        qualifying = _filter_qualifying(aggregates, threshold)
        if not qualifying:
            logger.info(
                f"No dimension group met the pattern threshold of {threshold} — "
                "skipping LLM pattern call."
            )
            return MacroPatternReport()

        summary_prompt = self._build_summary_prompt(aggregates, threshold)
        raw_patterns = self._call_llm(summary_prompt)

        report = MacroPatternReport()
        for raw in raw_patterns:
            detail = _raw_to_pattern_detail(raw, triage_results, enriched_exceptions)
            if detail is not None:
                report.patterns.append(detail)

        report.total_patterns = len(report.patterns)
        escalation_count = self._apply_escalations(report, triage_results, enriched_exceptions)
        report.total_escalations = escalation_count

        logger.info(
            f"Pattern analysis complete: {report.total_patterns} patterns identified, "
            f"{escalation_count} escalations applied."
        )
        return report

    def _build_aggregates(
        self,
        triage_results: List[TriageResult],
        enriched_exceptions: List[EnrichedExceptionSchema],
    ) -> Dict[str, Dict[str, dict]]:
        """Aggregate exception counts by vendor, region, category, and dc.

        Returns:
            Dict with keys "vendor", "region", "category", "dc".
            Each value is a dict mapping group_key → {count, critical_count, high_count, exception_ids}.
        """
        vendor: Dict[str, dict] = defaultdict(lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []})
        region: Dict[str, dict] = defaultdict(lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []})
        category: Dict[str, dict] = defaultdict(lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []})
        dc: Dict[str, dict] = defaultdict(lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []})

        for tr, ex in zip(triage_results, enriched_exceptions):
            eid = tr.exception_id
            is_critical = tr.priority == Priority.CRITICAL
            is_high = tr.priority == Priority.HIGH

            def _update(bucket: Dict[str, dict], key: Optional[str]) -> None:
                if key is None:
                    return
                bucket[key]["count"] += 1
                bucket[key]["exception_ids"].append(eid)
                if is_critical:
                    bucket[key]["critical_count"] += 1
                if is_high:
                    bucket[key]["high_count"] += 1

            _update(vendor, ex.vendor_id)
            _update(region, ex.region)
            _update(category, ex.category)
            # dc_id derived from store_id prefix (e.g. STR-001 → no dc field on enriched schema)
            # Use region as DC_LANE proxy when no explicit dc field is available

        return {
            "vendor": dict(vendor),
            "region": dict(region),
            "category": dict(category),
            "dc": dict(dc),
        }

    @staticmethod
    def _build_summary_prompt(
        aggregates: Dict[str, Dict[str, dict]], threshold: int
    ) -> str:
        """Format the macro summary prompt for the LLM.

        Only includes groups that meet or exceed the threshold.
        """
        lines = [
            "Here is a summary of today's exception run across all batches.",
            f"Identify systemic patterns where {threshold}+ exceptions share a single root cause.",
            "",
        ]

        def _section(title: str, bucket: Dict[str, dict]) -> None:
            qualifying = {k: v for k, v in bucket.items() if v["count"] >= threshold}
            if not qualifying:
                return
            lines.append(f"BY {title}:")
            for key, stats in sorted(qualifying.items(), key=lambda x: -x[1]["count"]):
                lines.append(
                    f"  {key}: {stats['count']} exceptions, "
                    f"{stats['critical_count']} CRITICAL, {stats['high_count']} HIGH"
                )
            lines.append("")

        _section("VENDOR", aggregates["vendor"])
        _section("REGION", aggregates["region"])
        _section("CATEGORY", aggregates["category"])
        _section("DC LANE", aggregates["dc"])

        lines.append(
            "Return a JSON array of pattern objects with fields: "
            "pattern_type, group_key, count, description. "
            "Return [] if no systemic patterns are present."
        )
        return "\n".join(lines)

    def _call_llm(self, summary_prompt: str) -> List[dict]:
        """Call the LLM with the macro summary and parse JSON pattern list.

        Returns:
            List of raw pattern dicts from the LLM. Empty list on parse failure.
        """
        try:
            response = self._provider.complete(_PATTERN_SYSTEM_PROMPT, summary_prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                text = "\n".join(inner)
            data = json.loads(text)
            if not isinstance(data, list):
                logger.warning(
                    f"PatternAnalyzer LLM returned non-list JSON: {type(data).__name__}. "
                    "Returning empty pattern list."
                )
                return []
            return [item for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"PatternAnalyzer LLM response parse failed: {exc}. Returning empty pattern list.")
            return []
        except Exception as exc:
            logger.error(f"PatternAnalyzer LLM call failed unexpectedly: {exc}. Returning empty pattern list.")
            return []

    def _apply_escalations(
        self,
        pattern_report: MacroPatternReport,
        triage_results: List[TriageResult],
        enriched_exceptions: List[EnrichedExceptionSchema],
    ) -> int:
        """Mutate triage_results: set pattern_id and escalate MEDIUM → HIGH.

        For each confirmed pattern, find all TriageResult objects whose enriched
        counterpart belongs to the pattern group, set pattern_id, and upgrade
        priority from MEDIUM to HIGH.

        Returns:
            Number of escalations applied.
        """
        escalation_count = 0
        # Build lookup: exception_id → enriched exception
        enriched_by_id = {ex.exception_id: ex for ex in enriched_exceptions}

        for pattern in pattern_report.patterns:
            group_key = pattern.group_key
            pattern_type = pattern.pattern_type

            for tr in triage_results:
                ex = enriched_by_id.get(tr.exception_id)
                if ex is None:
                    continue

                match = _matches_pattern(ex, pattern_type, group_key)
                if not match:
                    continue

                tr.pattern_id = pattern.pattern_id
                if tr.priority == Priority.MEDIUM:
                    tr.escalated_from = Priority.MEDIUM.value
                    tr.priority = Priority.HIGH
                    escalation_count += 1
                    pattern.escalation_count += 1
                    logger.debug(
                        f"Escalated {tr.exception_id} MEDIUM→HIGH (pattern {pattern.pattern_id})"
                    )

        return escalation_count


# --- Module-level helpers ---

def _filter_qualifying(
    aggregates: Dict[str, Dict[str, dict]], threshold: int
) -> bool:
    """Return True if any group in any dimension meets the threshold."""
    for bucket in aggregates.values():
        for stats in bucket.values():
            if stats["count"] >= threshold:
                return True
    return False


def _raw_to_pattern_detail(
    raw: dict,
    triage_results: List[TriageResult],
    enriched_exceptions: List[EnrichedExceptionSchema],
) -> Optional[PatternDetail]:
    """Convert a raw LLM pattern dict to a PatternDetail, with affected exception IDs."""
    try:
        pattern_type = PatternType(raw["pattern_type"])
    except (KeyError, ValueError):
        logger.warning(f"Invalid pattern_type in LLM response: {raw.get('pattern_type')!r}. Skipping.")
        return None

    group_key = raw.get("group_key", "")
    count = raw.get("count", 0)
    description = raw.get("description", "")

    # Find exception IDs belonging to this pattern group
    enriched_by_id = {ex.exception_id: ex for ex in enriched_exceptions}
    affected_ids = []
    critical_count = 0
    high_count = 0

    for tr in triage_results:
        ex = enriched_by_id.get(tr.exception_id)
        if ex is None:
            continue
        if _matches_pattern(ex, pattern_type, group_key):
            affected_ids.append(tr.exception_id)
            if tr.priority == Priority.CRITICAL:
                critical_count += 1
            elif tr.priority == Priority.HIGH:
                high_count += 1

    import uuid
    pattern_id = f"PAT-{str(uuid.uuid4())[:8].upper()}"

    return PatternDetail(
        pattern_id=pattern_id,
        pattern_type=pattern_type,
        group_key=group_key,
        affected_count=len(affected_ids),
        critical_count=critical_count,
        high_count=high_count,
        description=description,
        escalation_count=0,
        affected_exception_ids=affected_ids,
    )


def _matches_pattern(
    ex: EnrichedExceptionSchema,
    pattern_type: PatternType,
    group_key: str,
) -> bool:
    """Return True if this enriched exception belongs to the pattern group."""
    if pattern_type == PatternType.VENDOR:
        return ex.vendor_id == group_key
    if pattern_type == PatternType.REGION:
        return ex.region == group_key
    if pattern_type == PatternType.CATEGORY:
        return ex.category == group_key
    if pattern_type == PatternType.DC_LANE:
        return ex.region == group_key  # DC lane proxied by region
    if pattern_type == PatternType.MACRO:
        return True  # MACRO patterns affect all exceptions
    return False
```

- [ ] **Step 4: Run Task 1 tests**

```bash
cd /Users/MKunta/CODE/AI-driven-replenishment-exception-triage-agent
source .venv/bin/activate
pytest tests/test_pattern_analyzer.py::TestPatternAnalyzerInit tests/test_pattern_analyzer.py::TestBuildAggregates -v
```

Expected: 7 PASSED

- [ ] **Step 5: Run full suite — no regressions**

```bash
pytest tests/ --tb=short 2>&1 | tail -5
```

Expected: 195 + 7 = 202 tests passing

- [ ] **Step 6: Commit**

```bash
git add src/agent/pattern_analyzer.py tests/test_pattern_analyzer.py
git commit -m "feat: add PatternAnalyzer scaffold — init, _build_aggregates; 7 tests passing"
```

---

## Task 2: _build_summary_prompt

**Files:**
- Modify: `tests/test_pattern_analyzer.py` — add `TestBuildSummaryPrompt`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pattern_analyzer.py`:

```python
class TestBuildSummaryPrompt:
    @patch("src.agent.pattern_analyzer.get_provider")
    def test_includes_qualifying_vendor_section(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config(pattern_threshold=3))

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
```

- [ ] **Step 2: Run tests to confirm they pass** (implementation already present from Task 1)

```bash
pytest tests/test_pattern_analyzer.py::TestBuildSummaryPrompt -v
```

Expected: 5 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/test_pattern_analyzer.py
git commit -m "test: add TestBuildSummaryPrompt — prompt format and threshold filtering"
```

---

## Task 3: _call_llm — happy path and error handling

**Files:**
- Modify: `tests/test_pattern_analyzer.py` — add `TestCallLlm`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pattern_analyzer.py`:

```python
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
```

- [ ] **Step 2: Run to confirm they pass** (already implemented)

```bash
pytest tests/test_pattern_analyzer.py::TestCallLlm -v
```

Expected: 6 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/test_pattern_analyzer.py
git commit -m "test: add TestCallLlm — happy path, fence strip, error resilience"
```

---

## Task 4: _apply_escalations + analyze() integration

**Files:**
- Modify: `tests/test_pattern_analyzer.py` — add `TestApplyEscalations` and `TestAnalyze`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pattern_analyzer.py`:

```python
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
        assert triage[2].priority == Priority.HIGH  # was already HIGH — unchanged
        assert triage[2].escalated_from is None      # not escalated, just pattern-tagged

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
        assert triage[0].priority == Priority.CRITICAL  # unchanged

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
        assert triage[0].priority == Priority.LOW  # unchanged

    @patch("src.agent.pattern_analyzer.get_provider")
    def test_sets_pattern_id_on_all_members_even_non_escalated(self, mock_get_provider):
        mock_get_provider.return_value = MagicMock()
        from src.agent.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer(_make_config())

        triage = [
            _make_triage_result("exc-001", Priority.HIGH),    # already HIGH
            _make_triage_result("exc-002", Priority.MEDIUM),  # will be escalated
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
        """Only 2 exceptions per vendor — threshold is 3 — no LLM call should be made."""
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
        """3 exceptions from same vendor; 2 are MEDIUM → both escalated to HIGH."""
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
        assert triage[2].priority == Priority.HIGH  # was HIGH, unchanged

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
        """Even if 3 dimensions qualify, the LLM is called exactly once."""
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
```

- [ ] **Step 2: Run to confirm they pass**

```bash
pytest tests/test_pattern_analyzer.py::TestApplyEscalations tests/test_pattern_analyzer.py::TestAnalyze -v
```

Expected: 9 PASSED

- [ ] **Step 3: Run the full project test suite**

```bash
pytest tests/ --tb=short 2>&1 | tail -5
```

Expected: All 195 + 27 = 222 tests passing

- [ ] **Step 4: Commit**

```bash
git add tests/test_pattern_analyzer.py
git commit -m "test: add TestApplyEscalations and TestAnalyze — full pattern_analyzer coverage"
```

---

## Self-Review

**Spec coverage check:**

| Requirement (from spec / CLAUDE.md) | Task covering it |
|--------------------------------------|-----------------|
| Aggregates by vendor_id, region, category | Task 1 (`_build_aggregates`) |
| Groups with ≥ threshold (default 3) flagged | Task 1 + Task 4 (`analyze` skips LLM when below threshold) |
| LLM called once with macro summary | Task 4 (`test_llm_called_once_regardless_of_pattern_count`) |
| Summary prompt includes BY VENDOR/REGION/CATEGORY sections | Task 2 |
| Sections omitted when below threshold | Task 2 |
| LLM response parsed as JSON array of patterns | Task 3 |
| Fence stripping on LLM response | Task 3 |
| Parse errors → empty list (non-blocking) | Task 3 |
| Provider exceptions → empty list (non-blocking) | Task 3 |
| Returns `MacroPatternReport` with `PatternDetail` objects | Task 4 |
| Escalates MEDIUM → HIGH for pattern members | Task 4 |
| Sets `pattern_id` on all members (escalated or not) | Task 4 |
| Does NOT downgrade CRITICAL or escalate LOW | Task 4 |
| `escalated_from` set only on actually-escalated results | Task 4 |
| `total_patterns` and `total_escalations` populated on report | Task 4 |
| Empty input → returns empty `MacroPatternReport`, no LLM call | Task 4 |

**Placeholder scan:** None found.

**Type consistency:**
- `_build_aggregates` returns `Dict[str, Dict[str, dict]]` — used in `_build_summary_prompt` and `analyze` ✓
- `_apply_escalations(report, triage, enriched) -> int` — return type matches test assertion ✓
- `PatternDetail.escalation_count` incremented in `_apply_escalations` ✓
- `_filter_qualifying` returns `bool` — used as early-exit guard in `analyze` ✓
