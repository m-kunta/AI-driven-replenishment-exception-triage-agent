import json
from datetime import date, datetime
import pytest

from src.models import (
    EnrichmentConfidence,
    Priority,
    TriageResult,
    TriageRunResult,
)
from src.output.router import PriorityRouter
from src.utils.config_loader import AppConfig


@pytest.fixture
def base_config(tmp_path):
    """Provides a basic AppConfig with a temp directory for output."""
    config = AppConfig()
    config.output.log_dir = str(tmp_path / "logs")
    return config


@pytest.fixture
def mock_run_result():
    """Generates a minimal TriageRunResult with 1 exception per tier."""
    results = [
        # CRITICAL
        TriageResult(
            exception_id="c1",
            priority=Priority.CRITICAL,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="Test",
            recommended_action="Test",
            financial_impact_statement="Test",
            planner_brief="Test",
            est_lost_sales_value=1000.0,
        ),
        # HIGH
        TriageResult(
            exception_id="h1",
            priority=Priority.HIGH,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="Test",
            recommended_action="Test",
            financial_impact_statement="Test",
            planner_brief="Test",
            est_lost_sales_value=500.0,
        ),
        # MEDIUM
        TriageResult(
            exception_id="m1",
            priority=Priority.MEDIUM,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="Test",
            recommended_action="Test",
            financial_impact_statement="Test",
            planner_brief="Test",
            est_lost_sales_value=200.0,
        ),
        # LOW
        TriageResult(
            exception_id="l1",
            priority=Priority.LOW,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="Test",
            recommended_action="Test",
            financial_impact_statement="Test",
            planner_brief="Test",
            est_lost_sales_value=10.0,
        )
    ]
    return TriageRunResult(
        run_id="test-run",
        run_date=date(2026, 4, 9),
        run_timestamp=datetime.now(),
        triage_results=results
    )


def test_router_generates_all_four_files(base_config, mock_run_result, tmp_path):
    router = PriorityRouter(base_config)
    paths = router.route(mock_run_result)

    assert len(paths) == 4
    for tier in Priority:
        assert tier in paths
        file_path = paths[tier]
        assert file_path.exists()
        assert file_path.name == f"{tier.value}_2026-04-09.json"


def test_router_sorting_descending_by_financial_value(base_config):
    # Setup HIGH exceptions with varying sales value
    results = [
        TriageResult(
            exception_id="h_low",
            priority=Priority.HIGH,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
            est_lost_sales_value=50.0,
        ),
        TriageResult(
            exception_id="h_mid",
            priority=Priority.HIGH,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
            est_lost_sales_value=150.0,
        ),
        TriageResult(
            exception_id="h_high",
            priority=Priority.HIGH,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
            est_lost_sales_value=1200.0,
        )
    ]
    run_result = TriageRunResult(
        run_id="test-sort",
        run_date=date(2026, 4, 9),
        run_timestamp=datetime.now(),
        triage_results=results
    )

    router = PriorityRouter(base_config)
    paths = router.route(run_result)
    
    with open(paths[Priority.HIGH], "r") as f:
        data = json.load(f)
        
    assert len(data) == 3
    # Verify order is 1200, 150, 50
    assert data[0]["exception_id"] == "h_high"
    assert data[1]["exception_id"] == "h_mid"
    assert data[2]["exception_id"] == "h_low"


def test_router_handles_none_financial_value(base_config):
    results = [
        TriageResult(
            exception_id="n_none",
            priority=Priority.MEDIUM,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
            est_lost_sales_value=None,
        ),
        TriageResult(
            exception_id="n_zero",
            priority=Priority.MEDIUM,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
            est_lost_sales_value=0.0,
        ),
        TriageResult(
            exception_id="n_twenty",
            priority=Priority.MEDIUM,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
            est_lost_sales_value=20.0,
        )
    ]
    run_result = TriageRunResult(
        run_id="test-none",
        run_date=date(2026, 4, 9),
        run_timestamp=datetime.now(),
        triage_results=results
    )

    router = PriorityRouter(base_config)
    paths = router.route(run_result)
    
    with open(paths[Priority.MEDIUM], "r") as f:
        data = json.load(f)
        
    assert len(data) == 3
    assert data[0]["exception_id"] == "n_twenty"
    # The order of None vs 0.0 might be stable depending on python sort, but either is acceptable
    # since both evaluate to 0.0 for sorting.
    assert data[1]["est_lost_sales_value"] in (0.0, None)
    assert data[2]["est_lost_sales_value"] in (0.0, None)


def test_router_empty_priority_tier(base_config):
    # Only supply a HIGH result, no CRITICAL
    results = [
        TriageResult(
            exception_id="h1",
            priority=Priority.HIGH,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
        )
    ]
    run_result = TriageRunResult(
        run_id="test-empty",
        run_date=date(2026, 4, 9),
        run_timestamp=datetime.now(),
        triage_results=results
    )
    
    router = PriorityRouter(base_config)
    paths = router.route(run_result)
    
    critical_path = paths[Priority.CRITICAL]
    assert critical_path.exists()
    
    with open(critical_path, "r") as f:
        data = json.load(f)
        
    assert data == []


def test_aggregate_count_preservation(base_config):
    # Create 50 results across different priorities
    results = []
    for i in range(50):
        priority = Priority.CRITICAL if i % 4 == 0 else \
                   Priority.HIGH if i % 4 == 1 else \
                   Priority.MEDIUM if i % 4 == 2 else \
                   Priority.LOW
        
        results.append(TriageResult(
            exception_id=f"e_{i}",
            priority=priority,
            confidence=EnrichmentConfidence.HIGH,
            root_cause="-",
            recommended_action="-",
            financial_impact_statement="-",
            planner_brief="-",
        ))
        
    run_result = TriageRunResult(
        run_id="test-agg",
        run_date=date(2026, 4, 9),
        run_timestamp=datetime.now(),
        triage_results=results
    )
    
    router = PriorityRouter(base_config)
    paths = router.route(run_result)
    
    total_written = 0
    for path in paths.values():
        with open(path, "r") as f:
            data = json.load(f)
            total_written += len(data)
            
    assert total_written == 50
