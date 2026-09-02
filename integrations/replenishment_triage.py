"""Deterministic evaluation target for the real replenishment triage agent."""

from __future__ import annotations

import json
import tempfile
from time import perf_counter
from pathlib import Path

import glassbox as gb
from glassbox.collector import Collector
from glassbox.eval.models import DecisionResult, EvidenceRecord, GoldenCase
from glassbox.store import Database, Repository

from src.agent.llm_provider import LLMProvider, LLMResponse
from src.agent.triage_agent import TriageAgent
from src.models import EnrichedExceptionSchema
from src.utils.config_loader import AppConfig


class _ScriptedProvider(LLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        del system_prompt, user_prompt
        return LLMResponse(text=self._response, input_tokens=10, output_tokens=10)


def run_case(case: GoldenCase) -> DecisionResult:
    """Run one case through the production orchestrator without network I/O."""
    exception = EnrichedExceptionSchema.model_validate(case.input)
    urgency = str(case.expected_labels["urgency"])
    action = "Do nothing" if urgency == "LOW" else "Review now"
    fixture = case.metadata.get("provider_response", {})
    if not isinstance(fixture, dict):
        raise ValueError("provider_response metadata must be a mapping")
    scripted = _ScriptedProvider(
        json.dumps(
            [
                {
                    "exception_id": exception.exception_id,
                    "priority": fixture.get("priority", urgency),
                    "confidence": fixture.get("confidence", "HIGH"),
                    "root_cause": fixture.get("root_cause", "Scripted test cause"),
                    "recommended_action": fixture.get("recommended_action", action),
                    "financial_impact_statement": fixture.get(
                        "financial_impact_statement", "Impact"
                    ),
                    "planner_brief": fixture.get(
                        "planner_brief", "Scripted planner rationale"
                    ),
                }
            ]
        )
    )
    config = AppConfig(agent={"provider": "ollama", "model": "test", "batch_size": 1})
    agent = TriageAgent(config)
    agent._batch_processor._provider = scripted
    agent._pattern_analyzer._provider = scripted
    with tempfile.TemporaryDirectory() as directory:
        database = Database.open(Path(directory) / "evaluation.sqlite3")
        collector = Collector(Repository(database))
        gb.init(agent="replenishment-triage", version="evaluation", collector=collector)
        try:
            started_at = perf_counter()
            run_result = agent.run([exception])
            latency_ms = (perf_counter() - started_at) * 1_000
            gb.flush(timeout=1.0)
            trace_id = database.connection.execute("SELECT trace_id FROM traces").fetchone()[0]
            stored = Repository(database).trace_tree(trace_id).decisions[0]
        finally:
            gb.shutdown(timeout=1.0)
            database.close()
        return DecisionResult(
            decision=dict(stored.event.recommendation),
            evidence=tuple(
                EvidenceRecord(
                    evidence_id=item.evidence_id,
                    fields={item.field_name: item.field_value},
                )
                for item in stored.evidence
            ),
            rationale_citations=stored.event.rationale_citations,
            alternatives_considered=stored.event.alternatives_considered,
            measurements={
                "latency_ms": latency_ms,
                "cost_usd": 0.0,
                "tokens": (
                    run_result.statistics.total_input_tokens
                    + run_result.statistics.total_output_tokens
                ),
            },
        )
