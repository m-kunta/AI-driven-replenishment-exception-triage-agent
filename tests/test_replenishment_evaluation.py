from pathlib import Path

import yaml

from glassbox.eval.models import GoldenCase
from glassbox.eval.runner import run_suite


def test_replenishment_target_runs_real_agent_with_scripted_provider() -> None:
    from integrations.replenishment_triage import run_case

    result = run_case(
        GoldenCase(
            case_id="critical-oos-001",
            input={
                "exception_id": "critical-oos-001",
                "item_id": "SKU-001",
                "item_name": "Test item",
                "store_id": "STORE-001",
                "store_name": "Test store",
                "exception_type": "OOS",
                "exception_date": "2026-09-01",
                "units_on_hand": 0,
                "days_of_supply": 0.0,
                "source_system": "golden",
                "batch_id": "golden-batch",
                "ingested_at": "2026-09-01T00:00:00Z",
            },
            expected_labels={"urgency": "CRITICAL"},
        )
    )

    assert result.decision["urgency"] == "CRITICAL"
    assert len(result.evidence) >= 3
    assert set(result.rationale_citations) == {item.evidence_id for item in result.evidence}


def test_replenishment_target_evidences_a_low_do_nothing_decision() -> None:
    from integrations.replenishment_triage import run_case

    case = GoldenCase.model_validate(
        yaml.safe_load(
            Path("goldens/replenishment_triage/cases/do_nothing.yaml").read_text()
        )
    )
    result = run_case(case)

    assert result.decision == {"urgency": "LOW", "action": "Do nothing"}
    assert len(result.evidence) >= 3
    assert len(result.alternatives_considered) >= 1


def test_seed_manifest_passes_through_the_generic_runner() -> None:
    summary = run_suite(Path("goldens/replenishment_triage/manifest.yaml"))

    assert summary["gates"]["passed"] is True
    assert summary["assertions"] == {
        "schema_valid": 1.0,
        "citations_resolve": 1.0,
        "evidence_present": 1.0,
        "alternatives_present": 1.0,
    }
