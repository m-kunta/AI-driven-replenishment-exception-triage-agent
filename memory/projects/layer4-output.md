# Layer 4 — Routing, Alerting & Output

**Status:** COMPLETE

**Why:** Layer 4 is the consumer of Layer 3's `TriageRunResult`. It transforms AI triage decisions into actionable planner artifacts.

## What Was Built

`src/output/` contains all four completed modules:

| File | Responsibility |
|------|---------------|
| `src/output/router.py` | Priority queue routing — separate CRITICAL/HIGH/MEDIUM/LOW queues |
| `src/output/alert_dispatcher.py` | CRITICAL SLA alerts via email/Slack/Teams (60-min SLA configured) |
| `src/output/briefing_generator.py` | Morning briefing document (top 10 exceptions, markdown or JSON) |
| `src/output/exception_logger.py` | Exception log for backtesting pipeline |

Also needed:
- `scripts/run_triage.py` — CLI entry point that wires all 4 layers end-to-end

## Config Points (already in config.yaml)
- `output.briefing_dir: output/briefings`
- `output.log_dir: output/logs`
- `output.format: markdown` (markdown | json | both)
- `output.max_exceptions_in_briefing: 10`
- `alerting.critical_sla_minutes: 60`
- Alert channels: email, Slack, Teams (all currently `enabled: false`)
- `backtest.outcome_check_weeks: [4, 8]`

## Input Contract from Layer 3
`TriageAgent(config).run(enriched_exceptions)` returns `TriageRunResult` which contains:
- `triage_results: List[TriageResult]` — all triage decisions
- `pattern_report: MacroPatternReport` — systemic patterns
- `statistics: RunStatistics` — counts, token usage, duration

## How to Apply
When working on Layer 4, start with `briefing_generator.py` (highest planner value), then `alert_dispatcher.py` (CRITICAL SLA compliance), then `router.py`, then `exception_logger.py`. Wire it all in `scripts/run_triage.py`.
