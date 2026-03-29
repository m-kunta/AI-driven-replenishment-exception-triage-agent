# 🤖 AI-Driven Replenishment Exception Triage Agent

> **Agentic AI that triages retail replenishment exceptions by business consequence — not magnitude.**

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-e92063.svg)](https://docs.pydantic.dev/)
[![Claude AI](https://img.shields.io/badge/Claude-AI-blueviolet.svg)](https://www.anthropic.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini-AI-4285F4.svg)](https://deepmind.google/technologies/gemini/)
[![Status](https://img.shields.io/badge/Status-Work%20In%20Progress-orange.svg)](#project-status)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Author:** Mohith Kunta  
**GitHub:** [github.com/m-kunta](https://github.com/m-kunta)  
**Domain:** Supply Chain Planning / Retail Replenishment

> This project is actively under development. Layer 1 is complete, and Layer 2 now provides a stable enriched-data handoff contract for the future AI layer. Layers 3-4 are not implemented yet.

---

## The Problem

Every morning, retail replenishment planners face hundreds of inventory exceptions — OOS alerts, low stock warnings, forecast variances, vendor failures. Traditional tools sort them by deviation size. But a 300% variance on a slow-moving Tier 4 store staple is far less urgent than a 30% variance on a Tier 1 store's promotional item running a live TPR.

**Planners are triaging the wrong exceptions first.**

This agent changes that by reasoning about **business consequence**: promo status, store tier, vendor health, competitor proximity, perishability, and financial impact — before a planner ever touches the queue.

---

## What It Does

The agent ingests raw replenishment exceptions, enriches them with 15+ contextual signals, and uses **Claude** to produce a prioritized, actionable triage output:

- 📋 **Priority assignment** — CRITICAL / HIGH / MEDIUM / LOW with reasoning
- 🔍 **Root cause** — AI-determined in plain English
- 💡 **Recommended action** — specific, planner-ready
- 💸 **Financial impact** — estimated lost sales and promo margin at risk
- 🚨 **Pattern detection** — systemic vendor, DC lane, category, or regional flags
- 👻 **Phantom inventory flags** — OOS + strong DC supply + high vendor fill rate
- 📨 **Morning briefing** — Markdown report routed to email/Slack/Teams

---

## Architecture — Four Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: Ingestion & Normalization   ← ✅ BUILT & TESTED       │
│           CSV → field mapping → type coercion → dedup            │
│           → quarantine → CanonicalException schema               │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: Context Enrichment          ← COMPLETE (stable handoff contract for Layer 3) │
│           Store master · Item master · Promo calendar            │
│           Vendor fill rates · DC inventory · Regional signals    │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: Claude Reasoning Engine    ← 🔲 NOT STARTED           │
│           Batched inference · TriageResult schema                 │
│           Chain-of-thought · Pattern escalation                  │
├──────────────────────────────────────────────────────────────────┤
│  Layer 4: Routing, Alerting & Output ← 🔲 NOT STARTED           │
│           Morning briefing · Email/Slack/Teams · JSON export     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Triage by consequence, not deviation** | A 10% OOS on a Tier 1 promo SKU outranks a 500% variance on a Tier 4 ambient staple |
| **Enrichment before AI** | Structured signals fed to Claude reduce hallucination and token waste vs. raw data |
| **Quarantine bad records** | Invalid rows are written to `output/logs/quarantine_*.json`, never silently dropped |
| **Batched Claude calls** | 30 exceptions per batch — tunable — to balance cost, latency, and context window |
| **Pattern detection post-triage** | After individual triage, group by vendor/dc/category and escalate if ≥ 3 share a failure mode |

---

## Exception Types

| Type | Description |
|---|---|
| `OOS` | Out-of-stock — zero units on hand |
| `LOW_STOCK` | Approaching stockout, days of supply critically low |
| `FORECAST_VARIANCE` | Actual sales vs. forecast deviation |
| `ORDER_FAILURE` | Replenishment order not placed or failed |
| `VENDOR_LATE` | Inbound delivery past committed date |
| `DATA_INTEGRITY` | System discrepancy — units show on-hand but no sales |

---

## Project Structure

```
AI-driven-replenishment-exception-triage-agent/
├── src/
│   ├── models.py                  # All Pydantic schemas (all 4 layers)
│   ├── ingestion/
│   │   ├── base_adapter.py        # Abstract base: fetch(), validate_connection()
│   │   ├── csv_adapter.py         # CSV reader (BOM, delimiter, empty rows)
│   │   └── normalizer.py          # Field mapping, coercion, dedup, quarantine
│   ├── enrichment/                # ← Layer 2 (✅ BUILT & TESTED)
│   │   ├── data_loader.py         # Loads & indexes 6 reference datasets
│   │   └── engine.py              # EnrichmentEngine (joins + financials + scores)
│   ├── agent/                     # ← Layer 3 (NOT STARTED)
│   ├── output/                    # ← Layer 4 (NOT STARTED)
│   └── utils/
│       ├── config_loader.py       # YAML + ${ENV_VAR} resolution → AppConfig
│       ├── validators.py          # Pydantic validators
│       ├── logger.py              # loguru setup
│       └── exceptions.py         # Custom exception hierarchy
├── config/
│   └── config.yaml                # Full pipeline config (all 4 layers)
├── data/
│   ├── sample/                    # 6 CSVs — reproducible (seed=42)
│   │   ├── exceptions_sample.csv  # 120 rows with intentional triage scenarios
│   │   ├── store_master_sample.csv
│   │   ├── item_master_sample.csv
│   │   ├── promo_calendar_sample.csv
│   │   ├── vendor_performance_sample.csv
│   │   └── dc_inventory_sample.csv
│   └── regional_signals.json      # 2 active disruptions
├── tests/
│   ├── test_ingestion.py          # Ingestion layer tests
│   └── test_enrichment.py         # Layer 2 enrichment tests
├── scripts/
│   └── generate_sample_data.py    # Synthetic data generator
├── output/
│   ├── briefings/                 # Generated morning briefings (git-ignored)
│   └── logs/                      # Quarantine files + run logs (git-ignored)
├── requirements.txt
├── .env.example
└── CLAUDE.md                      # Developer context for Claude Code
```

---

## Sample Data Scenarios

The generated data (`scripts/generate_sample_data.py`) includes intentional scenarios designed to test triage quality:

| Scenario | What should happen |
|---|---|
| OOS + Tier 1 store (STR-001) + active TPR + nearby competitor | → `CRITICAL` |
| OOS at STR-005 + vendor fill rate 97% + DC has 35 days supply | → `PHANTOM` flag |
| 14 exceptions from VND-400 (fill rate 72%) | → `VENDOR` pattern escalation |
| 5 exceptions, high variance, Tier 4 stores, non-perishable | → `LOW` |

---

## Getting Started

### Prerequisites

- Python 3.9+
- An Anthropic API key (for Layer 3 — not yet needed for current Layer 1)

### Installation

```bash
git clone https://github.com/m-kunta/AI-driven-replenishment-exception-triage-agent.git
cd AI-driven-replenishment-exception-triage-agent

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: configure AI provider
cp .env.example .env
# Edit .env and add ANTHROPIC_API_KEY=...
```

### Generate Sample Data

```bash
python scripts/generate_sample_data.py
```

### Run Tests

```bash
./.venv/bin/pytest tests/ -v
# current suite should pass locally
```

### Verify Current Implemented Scope

The repository currently includes production-ready ingestion and a complete Layer 2 enrichment engine with a stable handoff contract for Layer 3.
These are the fastest checks to verify your environment end-to-end:

```bash
# 1) Regenerate deterministic sample data
python scripts/generate_sample_data.py

# 2) Validate ingestion layer
pytest tests/test_ingestion.py -v

# 3) Validate enrichment data loading contracts
pytest tests/test_enrichment.py -v
```

---

## Project Status

| Layer | Status | Details |
|---|---|---|
| **Layer 1 — Ingestion** | ✅ Complete | CSV adapter, normalizer, 25 tests passing |
| **Layer 2 — Enrichment** | ✅ Stable handoff contract | `DataLoader` + `EnrichmentEngine` emit validated enriched exceptions for Layer 3 |
| **Layer 3 — Claude Engine** | 🔲 Not Started | Batched inference, triage output, patterns |
| **Layer 4 — Output & Alerts** | 🔲 Not Started | Morning briefing, Slack/email routing |

### Layer 2 — Implementation

Layer 2 is fully implemented at `src/enrichment/`:

| File | Description |
|---|---|
| `src/enrichment/data_loader.py` | `DataLoader` — reads 6 reference datasets at startup into O(1) lookup dicts |
| `src/enrichment/engine.py` | `EnrichmentEngine` — joins each `CanonicalException` across all 6 sources, derives financial fields, assigns confidence |
| `tests/test_enrichment.py` | Tests covering each join, promo date logic, financial math, confidence scoring, and enriched schema validation |

**Join keys:**
- `store_id` → store tier, region, competitor signal
- `item_id` → category, perishability, vendor ID, price
- `(item_id, store_id)` → active promo, TPR depth (date-filtered)
- `vendor_id` → fill rate, open PO status
- `item_id` → DC days-of-supply, next receipt date
- `region` → active disruption flag (date-filtered)

**Key design choice:** `EnrichmentEngine` accepts a `reference_date` parameter (defaults to `date.today()`) so all date-sensitive checks (promo active, disruption active) are fully testable with a fixed date.

---

## Current Capabilities vs Planned

This project is intentionally staged. To avoid confusion, use this guide when evaluating what is runnable now:

| Area | Current State | Notes |
|---|---|---|
| Sample data generation | ✅ Implemented | `scripts/generate_sample_data.py` |
| CSV ingestion adapter | ✅ Implemented | UTF-8/BOM, delimiter support, empty-row handling |
| Canonical normalization | ✅ Implemented | Type coercion, dedup, quarantine |
| Enrichment data loading | ✅ Implemented | Loads and indexes store/item/promo/vendor/DC/regional sources |
| Full enrichment engine output | ✅ Stable Layer 2 contract | Current engine joins the implemented sources, computes financials, emits confidence/missing-field metadata, and includes `day_of_week_demand_index` for AI handoff |
| Claude triage agent loop | ⏳ Planned | Layer 3 not implemented yet |
| Routing/alerts/briefing outputs | ⏳ Planned | Layer 4 not implemented yet |
| CLI pipeline run (`run_triage.py`) | ⏳ Planned | Not yet available in `scripts/` |

If you are onboarding today, start with ingestion and data-loader tests before extending enrichment logic.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.9+ |
| Schemas | Pydantic v2 |
| AI | Anthropic Claude (`claude-sonnet-4`) |
| Config | YAML + `python-dotenv` |
| Logging | loguru |
| HTTP | httpx |
| Tests | pytest |

---

## Documentation Map

- `README.md`: project overview, status, and getting started
- `REPLENISHMENT_TRIAGE_AGENT_PROMPT.md`: full phased build spec and acceptance criteria
- `CLAUDE.md`: developer-focused context and implementation patterns
- `CONTRIBUTING.md`: contribution workflow, coding and test expectations

---

## Contributing

Contributions are welcome while the project moves through Layers 2–4.

1. Open an issue describing the scope (bug, enhancement, or missing task from the spec).
2. Keep changes focused to a single layer/task where possible.
3. Run the relevant test modules locally before opening a PR.
4. Update docs whenever behavior, interfaces, or status changes.

See `CONTRIBUTING.md` for detailed guidelines.

---

## License

Licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

## Author

**Mohith Kunta**  
Supply Chain & AI Portfolio  
🔗 [github.com/m-kunta](https://github.com/m-kunta)

---

*Built to solve the real problem planners face every morning: too many alerts, not enough signal.*
