# 🤖 AI-Driven Replenishment Exception Triage Agent

> **Agentic AI that triages retail replenishment exceptions by business consequence — not magnitude.**

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-e92063.svg)](https://docs.pydantic.dev/)
[![Claude AI](https://img.shields.io/badge/Claude-AI-blueviolet.svg)](https://www.anthropic.com/)
[![Status](https://img.shields.io/badge/Status-Work%20In%20Progress-orange.svg)](#project-status)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Author:** Mohith Kunta  
**GitHub:** [github.com/m-kunta](https://github.com/m-kunta)  
**Domain:** Supply Chain Planning / Retail Replenishment

> ⚠️ **This project is actively under development.** Layer 1 (Ingestion) is complete and tested. Layers 2–4 are in progress. See [Project Status](#project-status) for details.

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
│  Layer 2: Context Enrichment          ← 🔲 IN PROGRESS          │
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
│   ├── enrichment/                # ← Layer 2 (IN PROGRESS)
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
│   └── test_ingestion.py          # 25 tests — all passing
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
pytest tests/ -v
# 25 tests — all should pass
```

---

## Project Status

| Layer | Status | Details |
|---|---|---|
| **Layer 1 — Ingestion** | ✅ Complete | CSV adapter, normalizer, 25 tests passing |
| **Layer 2 — Enrichment** | 🔲 In Progress | Joining 6 contextual data sources |
| **Layer 3 — Claude Engine** | 🔲 Not Started | Batched inference, triage output, patterns |
| **Layer 4 — Output & Alerts** | 🔲 Not Started | Morning briefing, Slack/email routing |

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

## License

Licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

## Author

**Mohith Kunta**  
Supply Chain & AI Portfolio  
🔗 [github.com/m-kunta](https://github.com/m-kunta)

---

*Built to solve the real problem planners face every morning: too many alerts, not enough signal.*
