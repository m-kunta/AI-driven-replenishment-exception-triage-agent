# 🤖 AI-Driven Replenishment Exception Triage Agent

> **Agentic AI that triages retail replenishment exceptions by business consequence — not magnitude.**

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-e92063.svg)](https://docs.pydantic.dev/)
[![Claude AI](https://img.shields.io/badge/Claude-AI-blueviolet.svg)](https://www.anthropic.com/)
[![Gemini AI](https://img.shields.io/badge/Gemini-AI-4285F4.svg)](https://deepmind.google/technologies/gemini/)
[![Status](https://img.shields.io/badge/Status-Pipeline%20Complete-brightgreen.svg)](#project-status)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Author:** Mohith Kunta  
**GitHub:** [github.com/m-kunta](https://github.com/m-kunta)  
**Domain:** Supply Chain Planning / Retail Replenishment

> All four pipeline layers are complete and tested. The full pipeline runs end-to-end via `python scripts/run_triage.py`. Phase 8 (Backtesting) is fully implemented. Phase 11 (Web UI) MVP is live with a FastAPI backend, Next.js Command Center dashboard, BFF proxy for secure credential handling, and full Markdown briefing rendering. Phase 12 (Active Learning) is complete with analyst override submission, planner approval, and approved-override prompt injection. Phase 13 (Agentic Engagement) is now underway with manual action execution from the Command Center, typed backend action handling, adapter-driven delivery, and audit-tracked retry support.

---

## The Problem

Every morning, retail replenishment planners face hundreds of inventory exceptions — OOS alerts, low stock warnings, forecast variances, vendor failures. Traditional tools sort them by deviation size. But a 300% variance on a slow-moving Tier 4 store staple is far less urgent than a 30% variance on a Tier 1 store's promotional item running a live TPR.

**Planners are triaging the wrong exceptions first.**

This agent changes that by reasoning about **business consequence**: promo status, store tier, vendor health, competitor proximity, perishability, and financial impact — before a planner ever touches the queue.

---

## Business Context & Personas

### Who This Affects

| Persona | Role | Daily Pain Point |
|---|---|---|
| **Replenishment Planner** | Day-to-day inventory manager | Drowns in exception alerts, manually prioritizes by gut feeling, misses critical OOS on high-performing stores |
| **Supply Chain Manager** | Oversees regional operations | No visibility into systemic vendor/DC failures until they become major disruptions |
| **Category Manager** | Owns product portfolio | Can't distinguish inventory issues from promotional opportunities; reacts late to phantom inventory |
| **Store Manager** | Store-level operations | Suffers from stockouts on hero items during peak periods; no recourse when regional signals ignored |
| **Finance/Planning Director** | Strategic oversight | Unable to quantify true lost sales; reports based on magnitude not business impact |

### The Business Impact

- **Lost Sales**: A Tier 1 store OOS during a promoted period can cost $15,000–$50,000 in a single week
- **Customer Churn**: Stockouts on preferred items drive shoppers to competitors — especially for perishable categories
- **Vendor Accountability**: Systemic vendor failures go unnoticed until they cascade across regions
- **Planner Burnout**: Manual triage of 200+ exceptions daily leads to decision fatigue and inconsistent prioritization
- **Phantom Inventory**: "Phantom" stock (system shows inventory, but none on shelf) creates false confidence and missed replenishment opportunities

---

## Problem Statement

### The Core Issue

Retail replenishment systems generate exception alerts based on **statistical deviation** — how far actual inventory differs from forecast. However, this approach fundamentally misses the business reality:

> **A 10% variance on a Tier 1 store's promotional item is a crisis. A 500% variance on a Tier 4 store's slow-moving staple is noise.**

Current systems:
- ❌ Prioritize by magnitude, not business consequence
- ❌ Ignore contextual signals (promo status, store tier, vendor health, competitor proximity, perishability)
- ❌ Fail to detect systemic patterns (vendor failures, DC lane issues, category trends)
- ❌ Don't distinguish phantom inventory from real stockouts
- ❌ Produce unactionable alerts that planners must manually review

### What Success Looks Like

The ideal state is a **self-prioritizing exception queue** where:
- ✅ CRITICAL items (high business consequence) surface immediately
- ✅ LOW priority items (noise) are auto-relegated
- ✅ Root cause and recommended action are provided for each exception
- ✅ Financial impact (lost sales, margin at risk) is quantified
- ✅ Systemic patterns are detected and escalated before they become crises
- ✅ Phantom inventory is flagged and confirmed automatically
- ✅ A morning briefing summarizes everything in 5 minutes

---

## User-Facing Benefits

| Benefit | Impact |
|---|---|
| **Prioritized by Business Consequence** | Planners see the most important exceptions first — not the loudest |
| **Actionable Output** | Every exception includes root cause + recommended action — no more "figure it out" |
| **Financial Clarity** | Lost sales and margin-at-risk quantified — justifies action to leadership |
| **Pattern Detection** | Systemic vendor/DC/category issues flagged before they cascade |
| **Phantom Inventory Detection** | False OOS alerts identified and auto-corrected |
| **5-Minute Morning Briefing** | Entire daily queue summarized — read and act, not search and sort |
| **Multi-Channel Alerts** | CRITICAL alerts sent to Slack/Teams/Email with SLA timers |
| **Audit Trail** | Full CSV log of all decisions — compliance and continuous improvement |

---

## Detailed Use Cases

### Use Case 1: Promotional Stockout at High-Volume Store

**Scenario:**
- Store STR-001 (Tier 1, Los Angeles) has OOS on "Organic Oat Milk 64oz" — a featured item in an active TPR (40% off)
- Competitor Walmart is running a competing promo on their store-brand alternative
- Planner sees 15 OOS alerts at the top of their queue

**Without This Agent:**
- Planner manually checks promo calendar, store tier, competitor presence
- May deprioritize because "it's just one SKU" — missing the $28,000 lost sales potential
- Competitor captures customers during the 3-day gap

**With This Agent:**
- Agent enriches with: Tier 1, active TPR, competitor within 2 miles, perishable (dairy alternative)
- LLM reasons: "Tier 1 store + active TPR + competitor nearby + perishable = CRITICAL"
- Output includes: Lost sales estimate ($28K), recommended action ("Expedite from DC-502, override safety stock")
- Alert dispatched to planner's Slack with 2-hour SLA

---

### Use Case 2: Phantom Inventory Detection

**Scenario:**
- Store STR-005 shows OOS on "Premium Coffee Beans 2lb"
- System shows 0 units on-hand, planner receives OOS alert

**Without This Agent:**
- Planner creates expedited order, incurring $450 in rush shipping
- Delivery arrives, but shelves still empty — product was on-hand but hidden/damaged
- Waste: expedited cost + continued OOS

**With This Agent:**
- Agent enriches with: DC-102 has 35 days supply, vendor VND-125 has 97% fill rate, no recent warehouse discrepancy
- LLM flags as **POTENTIAL_PHANTOM_INVENTORY**
- Phantom webhook fires → API call to inventory system confirms actual on-shelf qty
- System confirms phantom: `phantom_confirmed: true`, exception type changes to `DATA_INTEGRITY`
- Planner notified: "False OOS — do not expedite, investigate shelf display"

---

### Use Case 3: Systemic Vendor Failure Pattern

**Scenario:**
- Planner receives 14 separate OOS alerts across 8 stores over 5 days
- Each alert shows different SKUs, different stores — appears as isolated incidents

**Without This Agent:**
- Each exception handled independently
- Vendor continues delivering 72% of orders — no escalation
- Problem compounds over weeks until category manager notices

**With This Agent:**
- Pattern analyzer groups 14 exceptions by vendor (VND-400, CleanHome Distributors)
- Calculates: vendor fill rate 72% (below threshold), failures span 3 DCs
- Escalation triggered → LLM generates pattern report: "Vendor CleanHome Distributors showing systemic deterioration"
- Morning briefing includes: "⚠️ VENDOR PATTERN — 14 exceptions from VND-400 (72% fill rate) — escalate to supply chain"
- Supply chain manager receives dedicated alert with vendor scorecard

---

### Use Case 4: Perishable Category Urgency

**Scenario:**
- Store STR-008 (Tier 2) shows LOW_STOCK on "Fresh Sourdough Bread" — 3 days of supply
- Same SKU shows LOW_STOCK at STR-012 (Tier 4) — also 3 days of supply

**Without This Agent:**
- Both appear equal priority — same days of supply
- Planner works through queue sequentially
- Fresh bread at Tier 2 (higher traffic) spoils while Tier 4 bread sits

**With This Agent:**
- Agent enriches with: perishable (shelf life 5 days), bakery category
- Tier 2 store has 3x the traffic of Tier 4
- LLM output: STR-008 = **HIGH** (fresh bakery, Tier 2, high traffic), STR-012 = **MEDIUM** (fresh bakery, Tier 4)
- Planner focuses on Tier 2 first — prevents $2,400 in potential shrink + lost sales

---

### Use Case 5: Regional Disruption Cascade

**Scenario:**
- Heavy storm warning issued for Pacific Northwest region
- 23 LOW_STOCK alerts appear across 12 stores in the region

**Without This Agent:**
- Each LOW_STOCK treated as independent
- Planner doesn't connect weather to inventory
- No proactive communication to store managers

**With This Agent:**
- Agent enriches with: regional signal "Pacific NW Storm Warning — 3-day disruption expected"
- All 23 exceptions flagged with regional context
- Pattern analyzer identifies 23 exceptions across 12 stores in same region
- Morning briefing includes: "🌧️ REGIONAL DISRUPTION — 23 exceptions in Pacific NW linked to storm — consider regional inventory hold"
- Supply chain manager notified to activate contingency routing

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
│  Layer 1: Ingestion & Normalization   ← ✅ COMPLETE                    │
│           CSV → field mapping → type coercion → dedup              │
│           → quarantine → CanonicalException schema                  │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: Context Enrichment          ← ✅ COMPLETE                    │
│           Store master · Item master · Promo calendar                │
│           Vendor fill rates · DC inventory · Regional signals        │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: Reasoning Engine            ← ✅ COMPLETE                    │
│           LLM Abstractions · Prompt System · Batch Processor         │
│           Pattern Analyzer · Phantom Webhook · Triage Orchestrator   │
├──────────────────────────────────────────────────────────────────┤
│  Layer 4: Routing, Alerting & Output  ← ✅ COMPLETE                    │
│  ✅ Priority Router · ✅ Alert Dispatcher (Email/Webhook/SLA)          │
│  ✅ Morning Briefing Generator · ✅ Exception Logger (CSV audit log)   │
├──────────────────────────────────────────────────────────────────┤
│  Main Orchestrator & CLI              ← ✅ COMPLETE                    │
│  ✅ src/main.py (4-layer pipeline) · ✅ scripts/run_triage.py (CLI)    │
├──────────────────────────────────────────────────────────────────┤
│  Phase 8: Backtesting Pipeline        ← ✅ COMPLETE                    │
│  ✅ scripts/run_backtest.py measures accuracy against true outcomes    │
├──────────────────────────────────────────────────────────────────┤
│  Phase 11: Web UI (Command Center)    ← ✅ MVP COMPLETE                  │
│  ✅ FastAPI Backend  · ✅ Next.js Dashboard (Markdown briefing)            │
│  ✅ BFF Proxy (server-side auth) · ✅ Exception queue + pipeline trigger  │
├──────────────────────────────────────────────────────────────────┤
│  Phase 12: Active Learning            ← ✅ COMPLETE                       │
│  ✅ Analyst override DB + API · ✅ Inline override submission             │
│  ✅ Planner review screen · ✅ Prompt learning loop + auto-approval       │
├──────────────────────────────────────────────────────────────────┤
│  Phase 13: Agentic Engagement        ← 🚧 IN PROGRESS                    │
│  ✅ Action modal + card history · ✅ FastAPI action endpoints             │
│  ✅ ActionStore + service + adapter · ✅ Retry + audit trail              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Triage by consequence, not deviation** | A 10% OOS on a Tier 1 promo SKU outranks a 500% variance on a Tier 4 ambient staple |
| **Enrichment before AI** | Structured signals fed to Claude reduce hallucination and token waste vs. raw data |
| **Quarantine bad records** | Invalid rows are written to `output/logs/quarantine_*.json`, never silently dropped |
| **Provider-agnostic AI engine** | Swap Claude/OpenAI/Gemini/Ollama with one config key; only selected provider's SDK is needed |
| **Batched LLM calls** | 30 exceptions per batch — tunable — to balance cost, latency, and context window |
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
│   ├── main.py                    # Full 4-layer pipeline orchestrator
│   ├── ingestion/
│   │   ├── base_adapter.py        # Abstract base: fetch(), validate_connection()
│   │   ├── csv_adapter.py         # CSV reader (BOM, delimiter, empty rows)
│   │   └── normalizer.py          # Field mapping, coercion, dedup, quarantine
│   ├── enrichment/                # ← Layer 2 (✅ COMPLETE)
│   │   ├── data_loader.py         # Loads & indexes 6 reference datasets
│   │   └── engine.py              # EnrichmentEngine (joins + financials + scores)
│   ├── agent/                     # ← Layer 3 (✅ COMPLETE)
│   │   ├── llm_provider.py        # Provider ABC + LLM abstractions
│   │   ├── prompt_composer.py     # Builds system + user prompts
│   │   ├── batch_processor.py     # Inference loop + JSON parser
│   │   ├── pattern_analyzer.py    # Aggregates + escalates patterns
│   │   ├── phantom_webhook.py     # HTTP POST for phantom inventory confirmation
│   │   └── triage_agent.py        # Full pipeline orchestrator (Task 5.4)
│   ├── output/                    # ← Layer 4 (✅ COMPLETE)
│   │   ├── router.py              # Partitions TriageRunResult into 4 priority JSON queue files
│   │   ├── alert_dispatcher.py    # Email/webhook/SLA timer alerts for CRITICAL & HIGH
│   │   ├── briefing_generator.py  # Daily markdown briefing with LLM executive summary
│   │   └── exception_logger.py    # Appends 26-field CSV audit row per exception; idempotent
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
├── prompts/                       # Modular prompt files for Layer 3
│   ├── system_prompt.md           # Senior planner persona
│   ├── triage_framework.md        # CRITICAL/HIGH/MEDIUM/LOW criteria
│   ├── output_contract.md         # JSON output schema + rules
│   ├── pattern_detection.md       # Vendor/DC/category/region pattern flags
│   ├── epistemic_honesty.md       # LOW confidence handling rules
│   ├── phantom_inventory.md       # Phantom detection signals
│   └── few_shot_library.json      # 5 annotated triage examples
├── tests/
│   ├── test_ingestion.py          # Layer 1 ingestion tests (35)
│   ├── test_enrichment.py         # Layer 2 enrichment tests (49)
│   ├── test_prompt_files.py       # Prompt structure validation (24)
│   ├── test_prompt_composer.py    # PromptComposer unit tests (14)
│   ├── test_llm_provider.py       # Provider factory + providers (13)
│   ├── test_phantom_webhook.py    # Phantom webhook tests (6)
│   ├── test_batch_processor.py    # Inference loop tests (32)
│   ├── test_pattern_analyzer.py   # Pattern aggregation tests (33)
│   ├── test_triage_agent.py       # Triage agent orchestrator tests (18)
│   ├── test_validators.py         # Schema validator tests (26)
│   ├── test_router.py             # Layer 4 priority router tests (5)
│   ├── test_alert_dispatcher.py   # Layer 4 alert dispatcher tests (10)
│   ├── test_briefing_generator.py # Layer 4 morning briefing tests (17)
│   ├── test_exception_logger.py   # Layer 4 exception logger tests (10)
│   └── test_main.py               # Main orchestrator + CLI tests (7)
├── frontend/                          # Phase 11-13 Web UI
│   ├── src/
│   │   ├── app/
│   │   │   ├── api/proxy/[...path]/   # BFF Route Handler (server-side auth)
│   │   │   │   └── route.ts
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx               # Command Center dashboard
│   │   │   ├── planner-review/        # Phase 12 planner approval screen
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── ActionModal.tsx        # Phase 13 action confirmation modal
│   │   │   ├── ExceptionCard.tsx      # Priority exception card + override/action entry points
│   │   │   └── MarkdownBriefing.tsx   # Styled Markdown renderer (GFM tables, etc.)
│   │   └── lib/
│   │       └── api.ts                 # Type-safe API client (queues, briefing, overrides, actions)
│   ├── __mocks__/                     # Jest manual mocks for ESM packages
│   │   ├── react-markdown.tsx
│   │   └── remark-gfm.ts
│   ├── next.config.ts
│   └── package.json
├── scripts/
│   ├── generate_sample_data.py    # Synthetic data generator
│   ├── run_triage.py              # CLI entry point for the full pipeline
│   └── run_backtest.py            # Backtesting pipeline evaluation script
├── output/
│   ├── backtest/                  # Generated backtest evaluation reports (git-ignored)
│   ├── briefings/                 # Generated morning briefings (git-ignored)
│   └── logs/                      # Quarantine files + exception audit log (git-ignored)
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
- An API key for your chosen AI provider (Claude, OpenAI, or Gemini) — or a running Ollama instance

### Installation

```bash
git clone https://github.com/m-kunta/AI-driven-replenishment-exception-triage-agent.git
cd AI-driven-replenishment-exception-triage-agent

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure AI provider
cp .env.example .env
# Edit .env — add the key for your chosen provider (ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY)
# Set provider: in config/config.yaml to match (claude / openai / gemini / ollama)
```

### Generate Sample Data

```bash
python scripts/generate_sample_data.py
```

### Run Tests

```bash
./.venv/bin/python -m pytest tests/ -v
# Targeted backend and frontend suites are expected to pass
```

### Run the Full Pipeline (CLI)

```bash
# Dry run — Layer 1+2 only, prints enrichment summary (no AI calls, no output files)
python scripts/run_triage.py --sample --dry-run

# Full pipeline — all 4 layers, no alert dispatch (safe for testing)
python scripts/run_triage.py --sample --no-alerts

# Full pipeline with alerts enabled (requires configured channels in config.yaml)
python scripts/run_triage.py --sample

# All CLI options
python scripts/run_triage.py --help
```

### Run the Web UI (Phase 11)

Start both the backend and frontend from the project root with a single command:

```bash
# 1. Copy and configure the root .env (one-time setup)
cp .env.example .env
# Edit .env — set API_PASSWORD, API_USERNAME, API_URL, and your AI provider key

# 2. Start both services (backend + frontend) together
bash scripts/dev.sh

# 3. Open http://localhost:3000
```

> **Note:** `scripts/dev.sh` exports the root `.env` into both processes. The
> Next.js BFF proxy (`/api/proxy/*`) reads credentials server-side — they are
> never sent to the browser bundle.

Or start individually for debugging:

```bash
source .env && uvicorn src.api.app:app --reload --port 8000
cd frontend && API_PASSWORD=yourpass API_USERNAME=admin npm run dev
```

### Run Backtesting Evaluation

```bash
# Evaluate historical triage outcomes for precision & recall grading
python scripts/run_backtest.py --date 2026-04-11 --week 4 --sample
```

---

## Project Status

| Layer | Status | Details |
|---|---|---|
| **Layer 1 — Ingestion** | ✅ Complete | CSV adapter, normalizer, 35 tests |
| **Layer 2 — Enrichment** | ✅ Complete | `DataLoader` + `EnrichmentEngine` with enriched exception output for Layer 3 |
| **Layer 3 — Reasoning Engine** | ✅ Complete | Prompt system, LLM abstractions, Phantom Webhook, Batch Processor, Pattern Analyzer, Triage Agent |
| **Layer 4 — Output & Alerts** | ✅ Complete | Priority Router · Alert Dispatcher · Morning Briefing · Exception Logger (CSV audit log) |
| **Main Orchestrator & CLI** | ✅ Complete | `src/main.py` wires all 4 layers; `scripts/run_triage.py` provides full CLI |
| **Phase 8 — Backtesting** | ✅ Complete | `scripts/run_backtest.py` — outcome accuracy scoring at Week 4/8 after exception date |
| **Phase 11 — Web UI** | ✅ MVP Complete | FastAPI backend + Next.js Command Center. BFF proxy keeps credentials server-side. Markdown briefing panel, exception queue tabs, and pipeline trigger are live. |
| **Phase 12 — Active Learning** | ✅ Complete | Analyst override DB layer, FastAPI override endpoints, analyst inline override modal, planner review screen, approved-override prompt injection, and startup auto-approval are live. |
| **Phase 13 — Agentic Engagement** | 🚧 In Progress | The first execution slice is live: action modal, exception-card action history, FastAPI action endpoints, `ActionStore`, action service/adapter, retry, audit logging, and planner-only gating for `STORE_CHECK` / `VENDOR_FOLLOW_UP`. Broader ERP-specific integrations and deeper RBAC remain ahead. |

### Layer 2 — Implementation

Layer 2 is fully implemented at `src/enrichment/`:

| File | Description |
|---|---|
| `src/enrichment/data_loader.py` | `DataLoader` — reads 6 reference datasets at startup into O(1) lookup dicts |
| `src/enrichment/engine.py` | `EnrichmentEngine` — joins each `CanonicalException` across all 6 sources, derives financial fields, assigns confidence, and degrades failed enrichments to `LOW` confidence with `missing_data_fields=["enrichment_failed"]` |
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
| Full enrichment engine output | ✅ Implemented | Joins all 6 sources, computes financials, emits confidence/missing-field metadata |
| Prompt system | ✅ Implemented | 6 modular prompt files + 5-example few-shot library |
| Multi-provider LLM abstraction | ✅ Implemented | Claude / OpenAI / Gemini / Ollama via single `get_provider()` factory |
| Phantom inventory webhook | ✅ Implemented | HTTP POST confirmation; mutates `TriageResult` on confirmed phantom |
| Batched inference loop | ✅ Implemented | `batch_processor.py` processes exceptions through LLM and validates JSON |
| Pattern analyzer | ✅ Implemented | `pattern_analyzer.py` aggregates and escalates systemic exceptions |
| Triage Agent orchestrator | ✅ Implemented | `triage_agent.py` orchestrates batch → phantom → pattern → `TriageRunResult` |
| Priority Router | ✅ Implemented | Partitions results into 4 priority JSON queue files sorted by financial impact |
| Alert Dispatcher | ✅ Implemented | Email/Slack/Teams/webhook alerts for CRITICAL & HIGH; per-exception SLA timer |
| Morning Briefing Generator | ✅ Implemented | Markdown briefing with LLM executive summary, exception cards, pattern report |
| Exception Logger | ✅ Implemented | 26-field CSV audit log per exception; idempotent on `(run_id, exception_id)` |
| CLI pipeline run | ✅ Implemented | `python scripts/run_triage.py [--sample] [--dry-run] [--no-alerts] [--verbose]` |
| Backtesting pipeline | ✅ Implemented | `scripts/run_backtest.py` — Week 4/8 outcome scoring |
| Web UI Backend (FastAPI) | ✅ Implemented | Exposes queues and triggers pipeline asynchronously (`src/api/app.py`) |
| Web UI Frontend (Next.js) | ✅ Implemented | Command Center dashboard: Markdown briefing panel (react-markdown + remark-gfm), exception queue tabs by priority, pipeline trigger, BFF proxy for secure server-side auth (`/frontend`) |
| Active Learning Override Workflow | ✅ Implemented | Analyst inline override submission, planner review screen, approval/rejection endpoints, and approved override feedback loop into prompt composition |
| Phase 13 Action Execution | 🚧 In Progress | Typed execution actions from the UI into backend action services with idempotent request IDs, authenticated requester injection, inline status/history, retry, and webhook-style adapter delivery |

Run `python scripts/run_triage.py --help` to see all available options.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.9+ |
| Schemas | Pydantic v2 |
| AI | Provider-agnostic — Claude / OpenAI / Gemini / Ollama |
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

Contributions are welcome as the project moves from completed pipeline and Active Learning work into deeper Phase 13 execution workflows and downstream system integrations.

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
