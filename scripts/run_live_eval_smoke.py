"""Run one opted-in live-provider Glassbox evaluation smoke case.

This command is intentionally outside the deterministic suite and refuses to
run unless LIVE_EVAL_ENABLED=1 is set. It is limited to one golden case.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import yaml

import glassbox as gb
from glassbox.collector import Collector
from glassbox.eval.models import GoldenCase
from glassbox.store import Database, Repository

from src.agent.triage_agent import TriageAgent
from src.models import EnrichedExceptionSchema
from src.utils.config_loader import load_config, validate_required_env_vars


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one live-provider evaluation smoke case")
    parser.add_argument("--case", required=True, type=Path, help="Golden-case YAML path")
    parser.add_argument(
        "--config", default="config/config.yaml", help="Agent configuration path"
    )
    arguments = parser.parse_args(argv)
    if os.environ.get("LIVE_EVAL_ENABLED") != "1":
        parser.error("refusing live evaluation; set LIVE_EVAL_ENABLED=1")

    case = GoldenCase.model_validate(yaml.safe_load(arguments.case.read_text()))
    config = load_config(arguments.config)
    validate_required_env_vars(config)
    exception = EnrichedExceptionSchema.model_validate(case.input)
    agent = TriageAgent(config)

    with tempfile.TemporaryDirectory() as directory:
        database = Database.open(Path(directory) / "live-evaluation.sqlite3")
        try:
            gb.init(agent="replenishment-triage", version="live-evaluation", collector=Collector(Repository(database)))
            agent.run([exception])
            if not gb.flush(timeout=30.0):
                raise RuntimeError("Glassbox collector did not flush within 30 seconds")
            trace_id = database.connection.execute("SELECT trace_id FROM traces").fetchone()[0]
            decision = Repository(database).trace_tree(trace_id).decisions[0]
        finally:
            gb.shutdown(timeout=5.0)
            database.close()
    print(json.dumps({"case_id": case.case_id, "decision": decision.event.recommendation}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
