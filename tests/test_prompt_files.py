"""Structural validation tests for prompt files (Task 4.1).

Author: Mohith Kunta <mohith.kunta@gmail.com>
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROMPTS_DIR = Path("prompts")

REQUIRED_MD_FILES = [
    "system_prompt.md",
    "triage_framework.md",
    "output_contract.md",
    "pattern_detection.md",
    "epistemic_honesty.md",
    "phantom_inventory.md",
]


class TestPromptFilesExist:
    def test_all_markdown_files_exist(self):
        for filename in REQUIRED_MD_FILES:
            path = PROMPTS_DIR / filename
            assert path.exists(), f"Missing required prompt file: {path}"

    def test_few_shot_library_exists(self):
        assert (PROMPTS_DIR / "few_shot_library.json").exists()


class TestFewShotLibrary:
    @pytest.fixture
    def examples(self):
        return json.loads((PROMPTS_DIR / "few_shot_library.json").read_text())

    def test_has_exactly_five_examples(self, examples):
        assert len(examples) == 5

    def test_each_example_has_required_keys(self, examples):
        for ex in examples:
            assert "id" in ex
            assert "description" in ex
            assert "exception" in ex
            assert "correct_output" in ex
            assert "reasoning" in ex

    def test_exception_objects_have_required_fields(self, examples):
        required = [
            "exception_id", "item_id", "item_name", "store_id", "store_name",
            "exception_type", "exception_date", "units_on_hand", "days_of_supply",
            "enrichment_confidence", "missing_data_fields",
        ]
        for ex in examples:
            for field in required:
                assert field in ex["exception"], (
                    f"Example {ex['id']} exception missing field: {field}"
                )

    def test_correct_output_has_required_fields(self, examples):
        required = [
            "exception_id", "priority", "confidence", "root_cause",
            "recommended_action", "financial_impact_statement", "planner_brief",
            "compounding_risks", "missing_data_flags", "phantom_flag",
        ]
        for ex in examples:
            for field in required:
                assert field in ex["correct_output"], (
                    f"Example {ex['id']} correct_output missing field: {field}"
                )

    def test_priorities_are_valid_values(self, examples):
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for ex in examples:
            assert ex["correct_output"]["priority"] in valid, (
                f"Example {ex['id']} has invalid priority: {ex['correct_output']['priority']}"
            )

    def test_covers_all_priority_levels(self, examples):
        priorities = {ex["correct_output"]["priority"] for ex in examples}
        assert "CRITICAL" in priorities
        assert "HIGH" in priorities
        assert "MEDIUM" in priorities
        assert "LOW" in priorities

    def test_phantom_flag_is_false_in_all_outputs(self, examples):
        for ex in examples:
            assert ex["correct_output"]["phantom_flag"] is False


class TestSystemPromptContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "system_prompt.md").read_text()

    def test_contains_supply_chain_persona(self, content):
        assert "supply chain" in content.lower()

    def test_contains_consequence_not_magnitude_principle(self, content):
        assert "consequence" in content.lower()
        assert "magnitude" in content.lower()


class TestTriageFrameworkContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "triage_framework.md").read_text()

    def test_contains_all_four_priority_tiers(self, content):
        for tier in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            assert tier in content

    def test_contains_escalation_rules(self, content):
        assert "escalat" in content.lower()


class TestOutputContractContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "output_contract.md").read_text()

    def test_specifies_json_array_return(self, content):
        assert "JSON array" in content

    def test_forbids_markdown_fences(self, content):
        assert "code fence" in content.lower() or "```" in content

    def test_contains_pattern_analysis_object(self, content):
        assert "pattern_analysis" in content

    def test_contains_all_triage_result_fields(self, content):
        required_fields = [
            "exception_id", "priority", "confidence", "root_cause",
            "recommended_action", "financial_impact_statement", "planner_brief",
            "compounding_risks", "missing_data_flags", "phantom_flag",
        ]
        for field in required_fields:
            assert field in content, f"Output contract missing field spec: {field}"


class TestPatternDetectionContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "pattern_detection.md").read_text()

    def test_contains_all_pattern_types(self, content):
        for pt in ["VENDOR", "DC_LANE", "CATEGORY", "REGION", "MACRO"]:
            assert pt in content

    def test_specifies_threshold(self, content):
        assert "3" in content


class TestEpistemicHonestyContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "epistemic_honesty.md").read_text()

    def test_contains_unknown_handling_rules(self, content):
        assert "UNKNOWN" in content

    def test_contains_low_confidence_rules(self, content):
        assert "LOW" in content


class TestPhantomInventoryContent:
    @pytest.fixture
    def content(self):
        return (PROMPTS_DIR / "phantom_inventory.md").read_text()

    def test_contains_phantom_signal_description(self, content):
        assert "fill rate" in content.lower() or "vendor_fill_rate" in content

    def test_contains_potential_phantom_flag(self, content):
        assert "POTENTIAL_PHANTOM_INVENTORY" in content

    def test_contains_recommended_action_language(self, content):
        assert "physical count" in content.lower()
