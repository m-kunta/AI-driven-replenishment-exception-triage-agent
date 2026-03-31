"""Prompt composer for the triage agent (Task 4.2).

Loads all prompt files at startup (cached in memory) and exposes:
- compose_system_prompt() -> str
- compose_user_prompt(batch, reasoning_trace_enabled) -> str

Usage:
    composer = PromptComposer()
    system = composer.compose_system_prompt()
    user = composer.compose_user_prompt(enriched_exceptions, reasoning_trace_enabled=False)

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from src.models import EnrichedExceptionSchema

PROMPTS_DIR = Path("prompts")

_REQUIRED_FILES = [
    "system_prompt.md",
    "triage_framework.md",
    "output_contract.md",
    "pattern_detection.md",
    "epistemic_honesty.md",
    "phantom_inventory.md",
    "few_shot_library.json",
]


class PromptComposer:
    """Loads prompt files and composes system/user prompts for any LLM provider."""

    def __init__(self, prompts_dir: Path = PROMPTS_DIR) -> None:
        self._prompts_dir = prompts_dir
        self._cache: dict[str, str] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load and cache all required prompt files at startup."""
        for filename in _REQUIRED_FILES:
            path = self._prompts_dir / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Required prompt file missing: {path}. "
                    "Run Task 4.1 to create all prompt files."
                )
            self._cache[filename] = path.read_text(encoding="utf-8")

    def _format_few_shots(self) -> str:
        """Format few-shot examples as a readable block for the system prompt."""
        examples = json.loads(self._cache["few_shot_library.json"])
        lines = ["## Few-Shot Examples\n"]
        for ex in examples:
            lines.append(f"### Example: {ex['description']}")
            lines.append(
                f"**Input exception:**\n```json\n"
                f"{json.dumps(ex['exception'], indent=2, default=str)}\n```"
            )
            lines.append(
                f"**Correct output:**\n```json\n"
                f"{json.dumps(ex['correct_output'], indent=2, default=str)}\n```"
            )
            lines.append(f"**Reasoning:** {ex['reasoning']}\n")
        return "\n".join(lines)

    def compose_system_prompt(self) -> str:
        """Assemble the full system prompt from all prompt blocks.

        Assembly order:
          1. system_prompt.md  (persona)
          2. triage_framework.md
          3. few_shot_library.json  (formatted examples)
          4. output_contract.md
          5. pattern_detection.md
          6. epistemic_honesty.md
          7. phantom_inventory.md

        Returns:
            Single string containing the full system prompt.
        """
        blocks = [
            self._cache["system_prompt.md"],
            self._cache["triage_framework.md"],
            self._format_few_shots(),
            self._cache["output_contract.md"],
            self._cache["pattern_detection.md"],
            self._cache["epistemic_honesty.md"],
            self._cache["phantom_inventory.md"],
        ]
        return "\n\n---\n\n".join(block.strip() for block in blocks)

    @staticmethod
    def _v(val: object) -> str:
        """Render a value as string; None becomes 'UNKNOWN'."""
        if val is None:
            return "UNKNOWN"
        return str(val)

    def _format_exception(
        self, exc: EnrichedExceptionSchema, n: int, total: int
    ) -> str:
        """Format a single enriched exception using the standard template."""
        promo_type_str = (
            exc.promo_type.value if exc.promo_type is not None else "UNKNOWN"
        )
        lost_sales = exc.est_lost_sales_value if exc.est_lost_sales_value is not None else 0.0
        promo_margin = exc.promo_margin_at_risk if exc.promo_margin_at_risk is not None else 0.0

        return (
            f"[EXCEPTION {n} of {total}]\n"
            f"exception_id: {exc.exception_id}\n"
            f"item: {exc.item_name} ({exc.item_id}) — velocity rank {self._v(exc.velocity_rank)} in {self._v(exc.category)}\n"
            f"store: {exc.store_id} ({exc.store_name}) — Tier {self._v(exc.store_tier)}, ${self._v(exc.weekly_store_sales_k)}K/week\n"
            f"exception_type: {exc.exception_type.value}\n"
            f"units_on_hand: {exc.units_on_hand} | days_of_supply: {exc.days_of_supply:.1f}\n"
            f"promo_active: {self._v(exc.promo_active)} | promo_type: {promo_type_str} | promo_end: {self._v(exc.promo_end_date)}\n"
            f"dc_inventory_days: {self._v(exc.dc_inventory_days)}\n"
            f"vendor_fill_rate_90d: {self._v(exc.vendor_fill_rate_90d)}% | open_po_inbound: {self._v(exc.open_po_inbound)} | next_delivery: {self._v(exc.next_delivery_date)}\n"
            f"lead_time_days: {self._v(exc.lead_time_days)}\n"
            f"competitor_proximity_miles: {self._v(exc.competitor_proximity_miles)} | competitor_event: {self._v(exc.competitor_event)}\n"
            f"perishable: {self._v(exc.perishable)}\n"
            f"day_of_week_demand_index: {self._v(exc.day_of_week_demand_index)}\n"
            f"est_lost_sales_value: ${lost_sales:.2f}\n"
            f"promo_margin_at_risk: ${promo_margin:.2f}\n"
            f"regional_disruption: {self._v(exc.regional_disruption_description)}\n"
            f"enrichment_confidence: {exc.enrichment_confidence.value}\n"
            f"missing_data_fields: {exc.missing_data_fields}\n"
            f"---"
        )

    def compose_user_prompt(
        self,
        batch: List[EnrichedExceptionSchema],
        reasoning_trace_enabled: bool = False,
    ) -> str:
        """Generate the user prompt for a batch of enriched exceptions.

        Args:
            batch: List of EnrichedExceptionSchema objects to triage.
            reasoning_trace_enabled: If True, appends an instruction asking the
                LLM to include a reasoning_trace field in each output object.

        Returns:
            Formatted user prompt string ready to send to any LLM provider.
        """
        total = len(batch)
        exception_blocks = "\n\n".join(
            self._format_exception(exc, i + 1, total)
            for i, exc in enumerate(batch)
        )
        prompt = (
            f"Triage the following {total} replenishment exceptions.\n\n"
            f"{exception_blocks}\n\n"
            "Return a JSON array with one object per exception, followed by the "
            "pattern_analysis object, as specified in the output contract."
        )
        if reasoning_trace_enabled:
            prompt += (
                '\n\nFor each exception, include a "reasoning_trace" field in your '
                "JSON output with your full chain of thought before reaching the "
                "priority decision. Maximum 150 words."
            )
        return prompt
