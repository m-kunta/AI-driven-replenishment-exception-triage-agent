# CLAUDE.md — Replenishment Exception Triage Agent

## Project Overview

AI-powered agentic system that ingests replenishment exceptions from retail planning systems, enriches with contextual business signals, and uses Claude to triage by **business consequence** (not magnitude). Outputs prioritized exception lists with action briefs, financial impact, pattern flags, and morning briefing documents.

**Spec document:** `REPLENISHMENT_TRIAGE_AGENT_PROMPT.md` — contains the full task list, schemas, architecture, and acceptance criteria for all phases.

## Architecture — Four Layers

```
Layer 1: Ingestion & Normalization    ← BUILT (CSV adapter + normalizer)
Layer 2: Context Enrichment           ← COMPLETE (DataLoader + EnrichmentEngine; stable handoff contract for Layer 3)
Layer 3: Reasoning Engine             ← COMPLETE (all components built: batch_processor, pattern_analyzer, phantom_webhook, triage_agent)
Layer 4: Routing, Alerting & Output   ← IN PROGRESS (router ✅, alert_dispatcher ✅, briefing_generator ✅, exception_logger 🔲, run_triage.py 🔲)
```

## Stack

- **Language:** Python 3.9+
- **Models:** Pydantic v2
- **Config:** YAML with `${ENV_VAR}` resolution
- **Logging:** loguru
- **HTTP:** httpx
- **DB:** SQLAlchemy (for SQL adapter, not yet built)
- **AI:** Provider-agnostic — Claude (Anthropic), OpenAI, Gemini, or Ollama; configured via `agent.provider` in `config.yaml`
- **Tests:** pytest

## Setup

```bash
source .venv/bin/activate
python scripts/generate_sample_data.py   # generates data/sample/*.csv
python -m pytest tests/ -v               # run tests
```

## Key Commands

```bash
# NOTE: 'pytest'/'python' aren't on PATH in non-interactive shells; use .venv/bin/python -m pytest
.venv/bin/python -m pytest tests/ -v                           # 292 tests, all passing
.venv/bin/python -m pytest tests/test_ingestion.py -v          # 25 ingestion tests
.venv/bin/python -m pytest tests/test_enrichment.py -v         # enrichment tests
.venv/bin/python -m pytest tests/test_llm_provider.py -v       # LLM provider abstraction tests
.venv/bin/python -m pytest tests/test_prompt_composer.py -v    # prompt composer tests
.venv/bin/python -m pytest tests/test_phantom_webhook.py -v    # phantom webhook tests
.venv/bin/python -m pytest tests/test_batch_processor.py -v    # inference loop tests
.venv/bin/python -m pytest tests/test_pattern_analyzer.py -v   # pattern aggregation tests
.venv/bin/python -m pytest tests/test_triage_agent.py -v       # triage agent orchestrator tests
.venv/bin/python -m pytest tests/test_router.py -v             # Layer 4 priority router tests
.venv/bin/python -m pytest tests/test_alert_dispatcher.py -v   # Layer 4 alert dispatcher tests
.venv/bin/python -m pytest tests/test_briefing_generator.py -v # Layer 4 morning briefing generator tests
.venv/bin/python scripts/generate_sample_data.py               # reproducible (fixed seed=42)
```

## Project Structure

```
src/
├── models.py                  # All Pydantic schemas (Canonical, Enriched, Triage, Pattern, etc.)
├── ingestion/
│   ├── base_adapter.py        # ABC: fetch(), validate_connection()
│   ├── csv_adapter.py         # CSV reader (BOM, delimiter, empty rows)
│   ├── normalizer.py          # Field mapping, type coercion, dedup, quarantine
│   ├── api_adapter.py         # NOT YET BUILT
│   └── sql_adapter.py         # NOT YET BUILT
├── enrichment/                # BUILT: data_loader.py + engine.py
├── agent/
│   ├── llm_provider.py        # BUILT: LLMProvider ABC + Claude/OpenAI/Gemini/Ollama + get_provider()
│   ├── prompt_composer.py     # BUILT: loads prompts/, assembles system+user prompts
│   ├── phantom_webhook.py     # BUILT: fires HTTP POST on POTENTIAL_PHANTOM_INVENTORY flag
│   ├── batch_processor.py     # BUILT: inference loop, API retry, JSON parse
│   ├── pattern_analyzer.py    # BUILT: aggregates anomalies & calls LLM to escalate
│   └── triage_agent.py        # BUILT: orchestrates batch→phantom→pattern→TriageRunResult
├── output/                    # Layer 4 — IN PROGRESS
│   ├── router.py              # BUILT: routes TriageRunResult into 4 priority JSON queue files
│   ├── alert_dispatcher.py    # BUILT: formats + dispatches CRITICAL/HIGH alerts (email, webhook); SLA timer
│   ├── briefing_generator.py  # BUILT: markdown briefing with LLM executive summary
│   └── exception_logger.py    # NOT YET BUILT
└── utils/
    ├── config_loader.py       # YAML + env var resolution → AppConfig (multi-provider)
    ├── validators.py          # Pydantic-based schema validators
    ├── logger.py              # loguru setup
    └── exceptions.py          # Custom exception hierarchy
config/
└── config.yaml                # Full config with all layer settings
prompts/
├── system_prompt.md           # AI persona block
├── triage_framework.md        # CRITICAL/HIGH/MEDIUM/LOW tier definitions
├── output_contract.md         # JSON output schema the LLM must follow
├── pattern_detection.md       # Pattern types, thresholds, escalation rules
├── epistemic_honesty.md       # UNKNOWN field handling, low-confidence rules
├── phantom_inventory.md       # Phantom detection signals and action language
└── few_shot_library.json      # 5 annotated examples (all priority levels)
data/
├── sample/                    # 6 CSVs generated by scripts/generate_sample_data.py
│   ├── exceptions_sample.csv  # 120 rows with intentional scenarios
│   ├── store_master_sample.csv
│   ├── item_master_sample.csv
│   ├── promo_calendar_sample.csv
│   ├── vendor_performance_sample.csv
│   └── dc_inventory_sample.csv
├── regional_signals.json      # 2 active disruptions
└── schema/
    └── canonical_exception_schema.json
```

## Sample Data Scenarios

The generated sample data includes intentional scenarios for testing triage quality:
- **CRITICAL:** OOS + Tier 1 store (STR-001) + active TPR + nearby competitor
- **Phantom inventory:** OOS at STR-005 but vendor fill rate 97%, DC has 35 days supply
- **Vendor pattern:** 14 exceptions from VND-400 (CleanHome Distributors, fill rate 72%)
- **LOW priority:** 5 exceptions with high variance but zero business risk (Tier 4 stores, non-perishable)

## Current Scope Notes

- `src/enrichment/data_loader.py` is implemented and validated by tests.
- `src/enrichment/engine.py` is implemented: joins all 6 reference sources, computes financials, emits confidence/missing-field metadata, and degrades failed enrichments to `LOW` confidence with `missing_data_fields=["enrichment_failed"]`. `day_of_week_demand_index` populated; `extra="forbid"` on models; enriched schema artifact at `data/schema/enriched_exception_schema.json`.
- `src/agent/llm_provider.py`: provider-agnostic LLM abstraction. Call `get_provider(config.agent)` to get an `LLMProvider` instance; call `.complete(system, user) -> LLMResponse` to invoke any supported model.
- `src/agent/prompt_composer.py`: `PromptComposer` loads all 7 files in `prompts/` at init. Call `compose_system_prompt()` + `compose_user_prompt(batch, reasoning_trace_enabled)` to build prompts ready for any provider.
- `src/agent/phantom_webhook.py`: `process_phantom_inventory(triage_result, config)` fires on `POTENTIAL_PHANTOM_INVENTORY` flag; 5s timeout; on `phantom_confirmed: true` sets `exception_type = DATA_INTEGRITY` and `priority = MEDIUM` (or webhook-provided level).
- `src/agent/batch_processor.py`: `BatchProcessor` loops over exceptions in chunks (default 30) using `prompt_composer` and `llm_provider`. Features built-in parse retries (1 attempt) and API backoff (3 attempts).
- `src/agent/pattern_analyzer.py`: `PatternAnalyzer` groups exceptions by `PatternType` (VENDOR, DC_LANE, CATEGORY, REGION), passes summaries to the LLM, and triggers priority escalation (e.g. MEDIUM → HIGH) for matching events.
- `src/agent/triage_agent.py`: `TriageAgent(config).run(enriched_exceptions)` orchestrates the full Layer 3 pipeline — batch inference → phantom webhook → pattern analysis → `TriageRunResult`. Entry point for Layer 4.
- `src/output/router.py`: `PriorityRouter(config).route(run_result)` partitions all `TriageResult` objects into 4 priority queue JSON files (`CRITICAL/HIGH/MEDIUM/LOW_{run_date}.json`) sorted descending by `est_lost_sales_value`. Returns `Dict[Priority, Path]`.
- `src/output/alert_dispatcher.py`: `AlertDispatcher(config).dispatch(run_result)` fires formatted plaintext alerts for all `CRITICAL` and `HIGH` exceptions across configured channels (Slack, Teams, generic webhook via `httpx`; SMTP email via `smtplib`). Channels are independently toggled in config. Spawns a daemon `threading.Timer` per actionable exception for SLA escalation if unacknowledged.
- `src/output/briefing_generator.py`: `BriefingGenerator(config).generate(run_result) -> Path` writes `output/briefings/briefing_{run_date}.md`. Calls LLM exactly once for a 3-4 sentence executive summary (top 5 CRITICAL + pattern report as context); all other sections (at-a-glance table, pattern list, critical cards, full queue table, run stats) are templated. Gracefully falls back if the LLM call fails.
- `scripts/run_triage.py` is not yet present (remaining Layer 4 work); use module-level tests for current verification.

## Multi-Provider LLM Configuration

Switch provider with a single config change — no code changes required:

```yaml
# config/config.yaml
agent:
  provider: claude        # claude | openai | gemini | ollama
  model: claude-sonnet-4-20250514
  anthropic_api_key: ${ANTHROPIC_API_KEY}   # set only the one you need
  openai_api_key: ${OPENAI_API_KEY}
  gemini_api_key: ${GEMINI_API_KEY}
  ollama_base_url: http://localhost:11434
```

## Implementation Patterns

- **Adapters** return raw `List[Dict]` — normalizer handles all type coercion
- **Normalizer** dedup key: `(item_id, store_id, exception_type, exception_date)`
- **Quarantine** writes invalid records to `output/logs/quarantine_{date}_{batch_id}.json`
- **Field mapping** in config allows source field names to differ from canonical names
- All imports use `from __future__ import annotations` for Python 3.9+ compatibility
- **`TriageResult` is mutable by design** — phantom webhook and pattern analyzer mutate fields (`exception_type`, `priority`, `phantom_flag`, `pattern_id`, `escalated_from`) after initial AI assignment
