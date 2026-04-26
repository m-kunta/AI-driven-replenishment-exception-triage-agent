# AGENTS.md — Domain Logic & Application Architecture

This document describes the **Replenishment Exception Triage Agent**'s business logic, application architecture, and operational domain.

## Project Overview
An AI-powered agentic system that ingests replenishment exceptions from retail planning systems, enriches them with contextual business signals, and uses AI (Claude, OpenAI, Gemini) to triage them by **business consequence**, rather than purely by statistical magnitude.

## Business Context & Problem
Retail replenishment systems generate exceptions based on actual vs. forecast deviations.
- A 10% variance on a Tier 1 store's promotional item is a crisis.
- A 500% variance on a Tier 4 store's slow-moving staple is noise.

Current systems prioritize by magnitude. This agent acts as a **Virtual Planner** that prioritizes by business impact, catching phantom inventory, systemic vendor issues, and critical promotional misses.

## Four-Layer Architecture
1. **Layer 1: Ingestion & Normalization**
   - Accept CSV, API, or SQL outputs and normalize them into a `CanonicalException`.
2. **Layer 2: Context Enrichment**
   - Join 6 reference datasets (Store master, item master, promo calendar, vendor performance, DC inventory, regional signals) to compute dynamic financial impact scores (`est_lost_sales_value`).
3. **Layer 3: Reasoning Engine (The Agent)**
   - Utilize prompt-composers and multi-provider LLMs. Processes exceptions asynchronously, detects macro-patterns (e.g., repeating vendor failures), and flags potential phantom inventory.
4. **Layer 4: Routing, Alerting & Output**
   - Generates priority queues (`CRITICAL`, `HIGH`, etc.), dispatches email/webhook alerts with SLA timers, and compiles a daily Markdown Morning Briefing.

## Web UI (Agentic Copilot)
The system has migrated from a CLI batch process to a Web UI Copilot. Phase 11 is complete and live.

- **Phase 11 — MVP Command Center** ✅ Complete: FastAPI backend (`src/api/`) + Next.js dashboard (`frontend/`). Command Center reads priority queues and morning briefings from pipeline output files. Credentials are kept server-side via a BFF proxy (`frontend/src/app/api/proxy/`) — never exposed to the browser bundle.
- **Phase 12 — Active Learning** ✅ Complete: Analyst override DB layer, FastAPI override endpoints, inline analyst submission UI, separate planner review screen, and approved-override prompt injection are all live. Pending overrides can also auto-promote at pipeline startup through the one-day TTL rule.
- **Phase 13 — Agentic Engagement** 🚧 In Progress: The first execution slice is now live with exception-card action entry points, a confirmation modal, typed FastAPI action endpoints, SQLite-backed action audit records, adapter-driven execution, inline action history/status, retry for failed actions, and planner-only gating for the execution-heavier `STORE_CHECK` / `VENDOR_FOLLOW_UP` actions. Broader ERP-specific adapters and deeper RBAC remain future expansion work.

### Phase 11 API Surface
| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | None | Liveness check |
| `GET /runs` | Basic | Lists available run dates from `output/logs/` |
| `GET /exceptions/queue/{priority}/{run_date}` | Basic | Returns priority queue JSON for a given date |
| `GET /briefing/{run_date}` | Basic | Returns morning briefing markdown for a given date |
| `POST /pipeline/trigger` | Basic | Triggers full pipeline run asynchronously via `BackgroundTasks` |

### Phase 13 API Surface
| Endpoint | Auth | Description |
|---|---|---|
| `POST /actions` | Basic | Creates an execution request, injects the authenticated username, persists the action record, and attempts adapter execution |
| `GET /actions/{exception_id}` | Basic | Returns action records for a specific exception card, newest first |
| `POST /actions/{request_id}/retry` | Basic | Retries a previously failed action request using the stored payload and metadata |

## Typical Data Scenarios
The agent must correctly handle these edge cases:
- **CRITICAL Scenario:** OOS + Tier 1 store + active TPR + nearby competitor.
- **Phantom Inventory:** OOS at Store but vendor fill rate is 97% and DC has 35 days remaining.
- **Vendor Pattern:** Multiple low-priority exceptions aggregating underneath a single struggling vendor.
