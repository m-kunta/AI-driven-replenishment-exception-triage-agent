"""Pattern analyzer for the triage agent (Task 5.2).

Pass 2 of the triage pipeline — runs after all batch results are collected.
Aggregates by vendor/region/category, calls LLM once with macro summary,
confirms patterns, and escalates MEDIUM→HIGH for pattern members.

NOTE: DC_LANE pattern detection is not yet supported. The enrichment layer
does not provide a dedicated DC identifier field, so DC_LANE cannot be
correctly matched. It remains a valid PatternType enum value (for future use)
but is excluded from aggregation, the summary prompt, and match logic.
LLM-hallucinated DC_LANE patterns are silently dropped (0 affected exceptions).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import Dict, List, Optional

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
    '{"pattern_type": "VENDOR|CATEGORY|REGION|MACRO", '
    '"group_key": "the vendor/category/region identifier", '
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
        """Initialize PatternAnalyzer, wiring the LLM provider."""
        self._config = config
        self._provider: LLMProvider = get_provider(config.agent)

    def analyze(
        self,
        triage_results: List[TriageResult],
        enriched_exceptions: List[EnrichedExceptionSchema],
    ) -> MacroPatternReport:
        """Run Pass 2 pattern analysis across all triage results.

        Args:
            triage_results: All TriageResult objects from batch processing,
                positionally aligned with enriched_exceptions.
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

        if not _filter_qualifying(aggregates, threshold):
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
        """Aggregate exception counts by vendor, region, and category.

        DC_LANE is intentionally excluded: the enrichment layer does not provide
        a dedicated DC identifier field, so DC_LANE cannot be correctly computed.

        Returns:
            Dict with keys "vendor", "region", "category".
            Each value maps group_key → {count, critical_count, high_count, exception_ids}.
        """
        vendor: Dict[str, dict] = defaultdict(
            lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []}
        )
        region: Dict[str, dict] = defaultdict(
            lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []}
        )
        category: Dict[str, dict] = defaultdict(
            lambda: {"count": 0, "critical_count": 0, "high_count": 0, "exception_ids": []}
        )

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

        return {
            "vendor": dict(vendor),
            "region": dict(region),
            "category": dict(category),
        }

    @staticmethod
    def _build_summary_prompt(
        aggregates: Dict[str, Dict[str, dict]], threshold: int
    ) -> str:
        """Format the macro summary prompt for the LLM.

        Only includes dimension groups that meet or exceed the threshold.
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
        # DC LANE intentionally omitted: no DC identifier field in enrichment layer

        lines.append(
            "Return a JSON array of pattern objects with fields: "
            "pattern_type, group_key, count, description. "
            "Return [] if no systemic patterns are present."
        )
        return "\n".join(lines)

    def _call_llm(self, summary_prompt: str) -> List[dict]:
        """Call the LLM with the macro summary and parse the JSON pattern list.

        Returns:
            List of raw pattern dicts. Empty list on any parse or network failure.
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
            logger.warning(
                f"PatternAnalyzer LLM response parse failed: {exc}. "
                "Returning empty pattern list."
            )
            return []
        except Exception as exc:
            logger.error(
                f"PatternAnalyzer LLM call failed unexpectedly: {exc}. "
                "Returning empty pattern list."
            )
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
        enriched_by_id = {ex.exception_id: ex for ex in enriched_exceptions}

        for pattern in pattern_report.patterns:
            group_key = pattern.group_key
            pattern_type = pattern.pattern_type

            for tr in triage_results:
                ex = enriched_by_id.get(tr.exception_id)
                if ex is None:
                    continue
                if not _matches_pattern(ex, pattern_type, group_key):
                    continue

                tr.pattern_id = pattern.pattern_id
                if tr.priority == Priority.MEDIUM:
                    tr.escalated_from = Priority.MEDIUM.value
                    tr.priority = Priority.HIGH
                    escalation_count += 1
                    pattern.escalation_count += 1
                    logger.debug(
                        f"Escalated {tr.exception_id} MEDIUM→HIGH "
                        f"(pattern {pattern.pattern_id})"
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
    """Convert a raw LLM pattern dict to a PatternDetail with affected exception IDs."""
    try:
        pattern_type = PatternType(raw["pattern_type"])
    except (KeyError, ValueError):
        logger.warning(
            f"Invalid pattern_type in LLM response: {raw.get('pattern_type')!r}. Skipping."
        )
        return None

    group_key = raw.get("group_key", "")
    description = raw.get("description", "")

    enriched_by_id = {ex.exception_id: ex for ex in enriched_exceptions}
    affected_ids: List[str] = []
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

    if not affected_ids:
        logger.debug(
            f"Pattern {pattern_type.value} / {group_key!r} matched 0 exceptions — skipping."
        )
        return None

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
    """Return True if this enriched exception belongs to the given pattern group."""
    if pattern_type == PatternType.VENDOR:
        return ex.vendor_id == group_key
    if pattern_type == PatternType.REGION:
        return ex.region == group_key
    if pattern_type == PatternType.CATEGORY:
        return ex.category == group_key
    # DC_LANE intentionally not handled: no DC identifier field in EnrichedExceptionSchema.
    # LLM-hallucinated DC_LANE patterns will match 0 exceptions and be dropped by the
    # zero-affected guard in _raw_to_pattern_detail.
    if pattern_type == PatternType.MACRO:
        return True
    return False
