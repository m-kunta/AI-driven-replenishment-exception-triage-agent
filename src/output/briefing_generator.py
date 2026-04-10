"""Morning briefing generator (Task 6.3).

Generates a markdown briefing document from a completed TriageRunResult.
Claude is called exactly once to produce the executive summary narrative;
all other content is templated from structured data.

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from src.agent.llm_provider import get_provider
from src.models import Priority, TriageResult, TriageRunResult
from src.utils.config_loader import AppConfig

logger = logging.getLogger(__name__)

_PRIORITY_ICON = {
    Priority.CRITICAL: "🔴",
    Priority.HIGH: "🟠",
    Priority.MEDIUM: "🟡",
    Priority.LOW: "🟢",
}

_EXECUTIVE_SUMMARY_SYSTEM = (
    "You are a supply chain analyst writing a concise executive briefing "
    "for a supply chain director. Be direct, specific, and avoid jargon."
)


class BriefingGenerator:
    """Generates a daily markdown briefing document from a TriageRunResult.

    Instantiate with AppConfig, then call generate() once per run.
    The output file is written to config.output.briefing_dir.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.briefing_dir = Path(config.output.briefing_dir)
        self.max_detail = config.output.max_exceptions_in_briefing

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, run_result: TriageRunResult) -> Path:
        """Generate and write the morning briefing document.

        Args:
            run_result: Completed triage run from Layer 3.

        Returns:
            Path to the written briefing file.
        """
        self.briefing_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.briefing_dir / f"briefing_{run_result.run_date}.md"

        content = self._render(run_result)

        output_path.write_text(content, encoding="utf-8")
        logger.info("Briefing written to %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _render(self, run_result: TriageRunResult) -> str:
        sections = [
            self._header(run_result),
            self._at_a_glance(run_result),
            self._patterns_section(run_result),
            self._executive_summary(run_result),
            self._top_critical(run_result),
            self._full_queue(run_result),
            self._run_stats(run_result),
        ]
        return "\n".join(sections)

    def _header(self, run_result: TriageRunResult) -> str:
        ts = run_result.run_timestamp.strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"# Replenishment Exception Triage — Morning Briefing\n"
            f"**Date:** {run_result.run_date} | "
            f"**Run ID:** {run_result.run_id} | "
            f"**Generated:** {ts}\n\n---\n"
        )

    def _at_a_glance(self, run_result: TriageRunResult) -> str:
        results = run_result.triage_results
        stats = run_result.statistics

        def _total_value(priority: Priority) -> float:
            return sum(
                (r.est_lost_sales_value or 0.0)
                for r in results
                if r.priority == priority
            )

        total_value = sum(r.est_lost_sales_value or 0.0 for r in results)

        rows = [
            f"| {_PRIORITY_ICON[Priority.CRITICAL]} CRITICAL | {stats.critical_count} | ${_total_value(Priority.CRITICAL):,.0f} |",
            f"| {_PRIORITY_ICON[Priority.HIGH]} HIGH | {stats.high_count} | ${_total_value(Priority.HIGH):,.0f} |",
            f"| {_PRIORITY_ICON[Priority.MEDIUM]} MEDIUM | {stats.medium_count} | ${_total_value(Priority.MEDIUM):,.0f} |",
            f"| {_PRIORITY_ICON[Priority.LOW]} LOW | {stats.low_count} | ${_total_value(Priority.LOW):,.0f} |",
            f"| **TOTAL** | **{stats.total_exceptions}** | **${total_value:,.0f}** |",
        ]
        table = "\n".join(rows)

        return (
            "## Today at a Glance\n"
            "| Priority | Count | Total Financial Exposure |\n"
            "|---|---|---|\n"
            f"{table}\n\n---\n"
        )

    def _patterns_section(self, run_result: TriageRunResult) -> str:
        report = run_result.pattern_report
        if not report.patterns:
            return "## Systemic Patterns Detected\nNo systemic patterns detected in this run.\n\n---\n"

        lines = ["## Systemic Patterns Detected\n"]
        for p in report.patterns:
            esc = f" ({p.escalation_count} escalations)" if p.escalation_count else ""
            lines.append(
                f"- **{p.pattern_type.value}** — `{p.group_key}`: "
                f"{p.affected_count} exceptions affected{esc}. {p.description}"
            )
        lines.append(f"\n_Total escalations applied: {report.total_escalations}_\n\n---\n")
        return "\n".join(lines)

    def _executive_summary(self, run_result: TriageRunResult) -> str:
        summary_text = self._call_llm_for_summary(run_result)
        return f"## Executive Summary\n{summary_text}\n\n---\n"

    def _call_llm_for_summary(self, run_result: TriageRunResult) -> str:
        """Call LLM once for a 3-4 sentence narrative. Falls back to template on error."""
        top_critical: List[TriageResult] = sorted(
            (r for r in run_result.triage_results if r.priority == Priority.CRITICAL),
            key=lambda r: r.est_lost_sales_value or 0.0,
            reverse=True,
        )[:5]

        # Build a compact context string for the LLM
        exception_lines = []
        for r in top_critical:
            item = r.item_name or r.exception_id
            store = r.store_name or r.store_id or "Unknown Store"
            exposure = f"${r.est_lost_sales_value or 0.0:,.0f}"
            exception_lines.append(f"- {item} at {store}: {r.root_cause} (exposure {exposure})")

        pattern_lines = []
        for p in run_result.pattern_report.patterns:
            pattern_lines.append(
                f"- {p.pattern_type.value} pattern: {p.group_key} — {p.description} "
                f"({p.affected_count} exceptions)"
            )

        if not exception_lines:
            # No CRITICAL — summarise HIGH instead
            top_high = sorted(
                (r for r in run_result.triage_results if r.priority == Priority.HIGH),
                key=lambda r: r.est_lost_sales_value or 0.0,
                reverse=True,
            )[:5]
            for r in top_high:
                item = r.item_name or r.exception_id
                store = r.store_name or r.store_id or "Unknown Store"
                exposure = f"${r.est_lost_sales_value or 0.0:,.0f}"
                exception_lines.append(f"- {item} at {store}: {r.root_cause} (exposure {exposure})")

        context_parts = []
        if exception_lines:
            label = "Top CRITICAL exceptions" if run_result.statistics.critical_count else "Top HIGH exceptions"
            context_parts.append(f"{label}:\n" + "\n".join(exception_lines))
        if pattern_lines:
            context_parts.append("Systemic patterns:\n" + "\n".join(pattern_lines))

        if not context_parts:
            return "_No significant exceptions to summarise for this run._"

        user_prompt = (
            "Write a 3-4 sentence executive summary of today's most critical supply chain "
            "situation for a supply chain director. Mention the highest-risk exception by name, "
            "the financial exposure, and the most important systemic pattern if one exists. "
            "Be direct and specific. No jargon.\n\n"
            + "\n\n".join(context_parts)
        )

        try:
            provider = get_provider(self.config.agent)
            response = provider.complete(_EXECUTIVE_SUMMARY_SYSTEM, user_prompt)
            logger.info(
                "Executive summary generated (%d input / %d output tokens)",
                response.input_tokens,
                response.output_tokens,
            )
            return response.text.strip()
        except Exception as exc:
            logger.warning("LLM call for executive summary failed: %s", exc)
            return (
                "_Executive summary generation failed — check LLM provider configuration. "
                f"({type(exc).__name__}: {exc})_"
            )

    def _top_critical(self, run_result: TriageRunResult) -> str:
        critical = sorted(
            (r for r in run_result.triage_results if r.priority == Priority.CRITICAL),
            key=lambda r: r.est_lost_sales_value or 0.0,
            reverse=True,
        )

        n = len(critical)
        if n == 0:
            return f"## Top Critical Exceptions\nNo CRITICAL exceptions in this run.\n\n---\n"

        lines = [f"## Top {n} Critical Exception{'s' if n != 1 else ''}\n"]

        for rank, r in enumerate(critical, start=1):
            days = f"{r.days_of_supply:.1f}" if r.days_of_supply is not None else "UNKNOWN"
            item = r.item_name or r.exception_id
            store = r.store_name or r.store_id or "Unknown"
            tier = f"Tier {r.store_tier}" if r.store_tier is not None else "Unknown Tier"
            exc_type = r.exception_type or "UNKNOWN"

            lines.append(f"### {rank}. {item} — {store}")
            lines.append(
                f"**Priority:** {_PRIORITY_ICON[Priority.CRITICAL]} CRITICAL | "
                f"**Confidence:** {r.confidence.value}"
            )
            lines.append(
                f"**Exception:** {exc_type} | **Store:** {tier} | "
                f"**Days of Supply:** {days}"
            )
            lines.append(
                f"**Financial Exposure:** ${r.est_lost_sales_value or 0.0:,.0f} lost sales | "
                f"${r.promo_margin_at_risk or 0.0:,.0f} promo margin"
            )
            lines.append(f"**Root Cause:** {r.root_cause}")
            lines.append(f"**Action Required:** {r.recommended_action}\n")
            lines.append(f"> {r.planner_brief}\n")

            if r.missing_data_flags:
                lines.append(f"⚠️ Missing data: {', '.join(r.missing_data_flags)}")
            if r.compounding_risks:
                lines.append(f"⚠️ Compounding risks: {', '.join(r.compounding_risks)}")

            lines.append("\n---\n")

        return "\n".join(lines)

    def _full_queue(self, run_result: TriageRunResult) -> str:
        all_results = sorted(
            run_result.triage_results,
            key=lambda r: (
                list(Priority).index(r.priority),
                -(r.est_lost_sales_value or 0.0),
            ),
        )

        rows = []
        for rank, r in enumerate(all_results, start=1):
            icon = _PRIORITY_ICON.get(r.priority, "")
            item = r.item_name or r.exception_id
            store = r.store_name or r.store_id or "—"
            exc_type = r.exception_type or "—"
            days = f"{r.days_of_supply:.1f}" if r.days_of_supply is not None else "—"
            exposure = f"${r.est_lost_sales_value or 0.0:,.0f}"
            action = (r.recommended_action[:60] + "…") if r.recommended_action and len(r.recommended_action) > 60 else (r.recommended_action or "—")
            rows.append(f"| {rank} | {icon} {r.priority.value} | {item} | {store} | {exc_type} | {days} | {exposure} | {action} |")

        table = "\n".join(rows)
        return (
            "## Full Exception Queue\n"
            "| # | Priority | Item | Store | Type | Days Supply | Exposure | Action |\n"
            "|---|---|---|---|---|---|---|---|\n"
            f"{table}\n\n---\n"
        )

    def _run_stats(self, run_result: TriageRunResult) -> str:
        s = run_result.statistics
        duration = f"{s.pipeline_duration_seconds:.1f}s"
        return (
            "## Run Statistics\n"
            f"- Total exceptions processed: {s.total_exceptions}\n"
            f"- Batches: {s.batches_completed} completed, {s.batches_failed} failed\n"
            f"- Pattern escalations applied: {s.pattern_escalations}\n"
            f"- Phantom inventory flags: {s.phantom_flags}\n"
            f"- Pipeline completion time: {duration}\n"
        )
