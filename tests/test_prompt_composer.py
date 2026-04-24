"""Tests for the prompt composer (Task 4.2).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models import (
    EnrichedExceptionSchema,
    EnrichmentConfidence,
    ExceptionType,
    PromoType,
)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Minimal prompt files for testing the composer in isolation."""
    (tmp_path / "system_prompt.md").write_text("You are a supply chain planner.")
    (tmp_path / "triage_framework.md").write_text("## Triage Framework\nCRITICAL: urgent action.")
    (tmp_path / "output_contract.md").write_text("## Output Contract\nReturn a JSON array.")
    (tmp_path / "pattern_detection.md").write_text("## Pattern Detection\nFlag 3+ exceptions.")
    (tmp_path / "epistemic_honesty.md").write_text("## Epistemic Honesty\nUNKNOWN means null.")
    (tmp_path / "phantom_inventory.md").write_text("## Phantom Inventory\nCheck fill rate.")
    few_shots = [
        {
            "id": "fs_001",
            "description": "Test example — LOW priority",
            "exception": {"exception_id": "test-exc-001"},
            "correct_output": {"priority": "LOW"},
            "reasoning": "No business risk.",
        }
    ]
    (tmp_path / "few_shot_library.json").write_text(json.dumps(few_shots))
    return tmp_path


@pytest.fixture
def composer(prompts_dir: Path):
    from src.agent.prompt_composer import PromptComposer
    return PromptComposer(prompts_dir=prompts_dir)


@pytest.fixture
def minimal_exception() -> EnrichedExceptionSchema:
    return EnrichedExceptionSchema(
        exception_id="test-exc-001",
        item_id="ITM-001",
        item_name="Test Item Alpha",
        store_id="STR-001",
        store_name="Test Store One",
        exception_type=ExceptionType.OOS,
        exception_date=date(2026, 3, 30),
        units_on_hand=0,
        days_of_supply=0.0,
        source_system="TestSystem",
        batch_id="batch-001",
        ingested_at=datetime(2026, 3, 30, 8, 0, 0),
        enrichment_confidence=EnrichmentConfidence.HIGH,
    )


@pytest.fixture
def fully_enriched_exception() -> EnrichedExceptionSchema:
    return EnrichedExceptionSchema(
        exception_id="test-exc-002",
        item_id="ITM-002",
        item_name="Organic Whole Milk 1gal",
        store_id="STR-001",
        store_name="Flagship Manhattan",
        exception_type=ExceptionType.OOS,
        exception_date=date(2026, 3, 30),
        units_on_hand=0,
        days_of_supply=0.0,
        source_system="BlueYonder",
        batch_id="batch-001",
        ingested_at=datetime(2026, 3, 30, 8, 0, 0),
        velocity_rank=1,
        category="Dairy & Eggs",
        store_tier=1,
        weekly_store_sales_k=2100.0,
        promo_active=True,
        promo_type=PromoType.TPR,
        promo_end_date=date(2026, 4, 5),
        tpr_depth_pct=15.0,
        dc_inventory_days=4.5,
        vendor_fill_rate_90d=91.0,
        open_po_inbound=True,
        next_delivery_date=date(2026, 4, 1),
        lead_time_days=2,
        competitor_proximity_miles=0.3,
        competitor_event="Competitor dairy promo through April 5",
        perishable=True,
        day_of_week_demand_index=1.22,
        est_lost_sales_value=1847.50,
        promo_margin_at_risk=341.79,
        regional_disruption_flag=False,
        enrichment_confidence=EnrichmentConfidence.HIGH,
    )


class TestPromptComposerInit:
    def test_raises_if_prompt_file_missing(self, tmp_path: Path):
        from src.agent.prompt_composer import PromptComposer
        # Create all files except phantom_inventory.md
        for name in ["system_prompt.md", "triage_framework.md", "output_contract.md",
                     "pattern_detection.md", "epistemic_honesty.md"]:
            (tmp_path / name).write_text("x")
        (tmp_path / "few_shot_library.json").write_text("[]")
        with pytest.raises(FileNotFoundError, match="phantom_inventory.md"):
            PromptComposer(prompts_dir=tmp_path)

    def test_raises_if_few_shot_library_missing(self, tmp_path: Path):
        from src.agent.prompt_composer import PromptComposer
        for name in ["system_prompt.md", "triage_framework.md", "output_contract.md",
                     "pattern_detection.md", "epistemic_honesty.md", "phantom_inventory.md"]:
            (tmp_path / name).write_text("x")
        # few_shot_library.json is missing
        with pytest.raises(FileNotFoundError, match="few_shot_library.json"):
            PromptComposer(prompts_dir=tmp_path)


class TestComposeSystemPrompt:
    def test_contains_all_six_prompt_sections(self, composer):
        system = composer.compose_system_prompt()
        assert "You are a supply chain planner." in system
        assert "Triage Framework" in system
        assert "Output Contract" in system
        assert "Pattern Detection" in system
        assert "Epistemic Honesty" in system
        assert "Phantom Inventory" in system

    def test_contains_few_shot_examples_section(self, composer):
        system = composer.compose_system_prompt()
        assert "Few-Shot Examples" in system
        assert "Test example" in system  # description from fixture

    def test_few_shots_inserted_between_framework_and_contract(self, composer):
        system = composer.compose_system_prompt()
        framework_pos = system.index("Triage Framework")
        few_shot_pos = system.index("Few-Shot Examples")
        contract_pos = system.index("Output Contract")
        assert framework_pos < few_shot_pos < contract_pos

    def test_uses_override_store_examples_when_present(self, prompts_dir: Path):
        from src.agent.prompt_composer import PromptComposer

        store = MagicMock()
        store.get_approved_few_shot_examples.return_value = [
            {
                "input": {"exception_id": "override-001"},
                "output": {"priority": "CRITICAL", "root_cause": "Planner corrected"},
            }
        ]

        composer = PromptComposer(prompts_dir=prompts_dir, override_store=store)
        system = composer.compose_system_prompt()

        assert "override-001" in system
        assert "Planner corrected" in system

    def test_falls_back_to_static_few_shots_when_override_store_empty(self, prompts_dir: Path):
        from src.agent.prompt_composer import PromptComposer

        store = MagicMock()
        store.get_approved_few_shot_examples.return_value = []

        composer = PromptComposer(prompts_dir=prompts_dir, override_store=store)
        system = composer.compose_system_prompt()

        assert "Test example" in system

    def test_approved_override_enters_prompt_examples(self, prompts_dir: Path):
        from src.agent.prompt_composer import PromptComposer
        from src.db.store import OverrideStore

        store = OverrideStore(":memory:")
        row_id = store.insert_override(
            exception_id="EXC-001",
            run_date="2026-04-23",
            analyst_username="analyst1",
            enriched_input_snapshot={"exception_id": "EXC-001"},
            override_priority="HIGH",
            analyst_note="Planner note",
        )
        store.approve_override(row_id, "planner1")

        composer = PromptComposer(prompts_dir=prompts_dir, override_store=store)
        system = composer.compose_system_prompt()

        assert "EXC-001" in system
        assert "Planner note" in system

    def test_system_prompt_within_token_budget(self):
        from src.agent.prompt_composer import PromptComposer
        real_composer = PromptComposer(prompts_dir=Path("prompts"))
        system = real_composer.compose_system_prompt()
        estimated_tokens = len(system) / 4
        assert estimated_tokens < 8000, (
            f"System prompt estimated at {estimated_tokens:.0f} tokens — exceeds 8000 limit"
        )


class TestComposeUserPrompt:
    def test_contains_exception_id(self, composer, minimal_exception):
        user = composer.compose_user_prompt([minimal_exception])
        assert minimal_exception.exception_id in user

    def test_contains_all_required_field_markers(self, composer, fully_enriched_exception):
        user = composer.compose_user_prompt([fully_enriched_exception])
        required_markers = [
            "exception_id:",
            "item:",
            "store:",
            "exception_type:",
            "units_on_hand:",
            "days_of_supply:",
            "promo_active:",
            "promo_type:",
            "promo_end:",
            "dc_inventory_days:",
            "vendor_fill_rate_90d:",
            "open_po_inbound:",
            "next_delivery:",
            "lead_time_days:",
            "competitor_proximity_miles:",
            "perishable:",
            "day_of_week_demand_index:",
            "est_lost_sales_value:",
            "promo_margin_at_risk:",
            "regional_disruption:",
            "enrichment_confidence:",
            "missing_data_fields:",
        ]
        for marker in required_markers:
            assert marker in user, f"User prompt missing field marker: {marker!r}"

    def test_null_enrichment_fields_render_as_UNKNOWN(self, composer, minimal_exception):
        user = composer.compose_user_prompt([minimal_exception])
        assert "UNKNOWN" in user
        assert "velocity rank UNKNOWN" in user

    def test_batch_header_shows_correct_count(self, composer, minimal_exception):
        batch = [minimal_exception] * 5
        user = composer.compose_user_prompt(batch)
        assert "5 replenishment exceptions" in user
        assert "[EXCEPTION 1 of 5]" in user
        assert "[EXCEPTION 5 of 5]" in user

    def test_exceptions_separated_by_dashes(self, composer, minimal_exception):
        batch = [minimal_exception, minimal_exception]
        user = composer.compose_user_prompt(batch)
        assert user.count("---") >= 2

    def test_reasoning_trace_flag_appends_instruction(self, composer, minimal_exception):
        user_without = composer.compose_user_prompt([minimal_exception], reasoning_trace_enabled=False)
        user_with = composer.compose_user_prompt([minimal_exception], reasoning_trace_enabled=True)
        assert "reasoning_trace" not in user_without
        assert "reasoning_trace" in user_with
        assert "150 words" in user_with

    def test_promo_type_none_renders_as_unknown(self, composer, minimal_exception):
        user = composer.compose_user_prompt([minimal_exception])
        assert "promo_type: UNKNOWN" in user

    def test_user_prompt_30_records_within_token_budget(self):
        from src.agent.prompt_composer import PromptComposer
        real_composer = PromptComposer(prompts_dir=Path("prompts"))
        exceptions = [
            EnrichedExceptionSchema(
                exception_id=f"test-{i:03d}",
                item_id=f"ITM-{i:03d}",
                item_name=f"Item {i}",
                store_id=f"STR-{i:03d}",
                store_name=f"Store {i}",
                exception_type=ExceptionType.OOS,
                exception_date=date(2026, 3, 30),
                units_on_hand=0,
                days_of_supply=0.0,
                source_system="TestSystem",
                batch_id="batch-001",
                ingested_at=datetime(2026, 3, 30, 8, 0, 0),
                enrichment_confidence=EnrichmentConfidence.HIGH,
            )
            for i in range(30)
        ]
        user = real_composer.compose_user_prompt(exceptions)
        estimated_tokens = len(user) / 4
        assert estimated_tokens < 6000, (
            f"30-record user prompt estimated at {estimated_tokens:.0f} tokens — exceeds 6000 limit"
        )
