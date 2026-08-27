"""Compatibility coverage for running the agent without optional Glassbox."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_triage_run_returns_domain_result_without_glassbox():
    """The representative mocked run still works when Glassbox cannot import."""
    script = textwrap.dedent(
        f"""
        import importlib.util
        import json
        import sys
        from datetime import date, datetime
        from unittest.mock import MagicMock

        project_root = {str(PROJECT_ROOT)!r}
        sys.path.insert(0, project_root)
        assert importlib.util.find_spec("glassbox") is None

        from src.agent.batch_processor import BatchProcessorResult
        from src.agent.triage_agent import TriageAgent
        from src.models import (
            EnrichedExceptionSchema,
            EnrichmentConfidence,
            ExceptionType,
            MacroPatternReport,
            Priority,
            TriageResult,
        )
        from src.utils.config_loader import AppConfig

        agent = TriageAgent(
            AppConfig(
                agent={{
                    "provider": "claude",
                    "anthropic_api_key": "test-anthropic-key",
                }}
            )
        )
        agent._batch_processor = MagicMock()
        agent._batch_processor.process.return_value = BatchProcessorResult(
            triage_results=[
                TriageResult(
                    exception_id="fallback-exception",
                    priority=Priority.HIGH,
                    confidence=EnrichmentConfidence.HIGH,
                    root_cause="test root cause",
                    recommended_action="test action",
                    financial_impact_statement="test financial impact",
                    planner_brief="test brief",
                )
            ],
            raw_pattern_analyses=[],
            batches_completed=1,
            batches_failed=0,
            total_input_tokens=10,
            total_output_tokens=5,
        )
        agent._pattern_analyzer = MagicMock()
        agent._pattern_analyzer.analyze.return_value = MacroPatternReport(
            patterns=[], total_patterns=0, total_escalations=0
        )

        result = agent.run(
            [
                EnrichedExceptionSchema(
                    exception_id="fallback-exception",
                    item_id="item-1",
                    item_name="Fallback item",
                    store_id="store-1",
                    store_name="Fallback store",
                    exception_type=ExceptionType.OOS,
                    exception_date=date(2026, 8, 27),
                    units_on_hand=0,
                    days_of_supply=0.0,
                    source_system="test",
                    batch_id="batch-1",
                    ingested_at=datetime(2026, 8, 27, 12, 0, 0),
                )
            ],
            run_date=date(2026, 8, 27),
        )
        print(json.dumps({{
            "run_date": result.run_date.isoformat(),
            "exception_id": result.triage_results[0].exception_id,
            "high_count": result.statistics.high_count,
            "total_exceptions": result.statistics.total_exceptions,
        }}))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        check=False,
        cwd=PROJECT_ROOT.parent,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "run_date": "2026-08-27",
        "exception_id": "fallback-exception",
        "high_count": 1,
        "total_exceptions": 1,
    }
