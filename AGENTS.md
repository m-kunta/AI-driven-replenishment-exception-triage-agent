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
- **Phase 13 — Agentic Engagement** 🚧 In Progress: The execution MVP is live with exception-card action entry points, a confirmation modal, typed FastAPI action endpoints, SQLite-backed action audit records, adapter-driven execution (including a real Slack webhook adapter used automatically when `SLACK_WEBHOOK_URL` is set, falling back to a mock adapter otherwise), inline action history/status, retry for failed actions, a global paginated/filterable Action History page (`/actions` in the frontend) covering actions across all exceptions and run dates, planner-only gating for the execution-heavier `STORE_CHECK` / `VENDOR_FOLLOW_UP` actions, planner-only override approval/rejection, an override-analytics endpoint + stats strip on the planner review screen, an in-memory pipeline run registry with live status polling on the dashboard, and a Settings surface that can inspect runtime provider/model configuration and verify currently available models. Authenticated actor metadata is resolved server-side either through per-user `API_USERS` credentials (each user has their own username/password/role) or, when that's unset, a legacy shared-password mode — the UI reads the current actor profile from the backend rather than build-time role flags. Multi-provider hardening is also in place for Claude, OpenAI, Gemini, and Ollama, including placeholder-key rejection and more actionable model/auth/quota/connectivity failures. A standalone `scripts/run_daily.py` supports cron-scheduled daily runs with Slack briefing dispatch. Broader ERP-specific adapters beyond the generic/Slack adapter boundary and fuller RBAC beyond the current planner/analyst gates remain future work.

### Phase 11 API Surface
| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | None | Liveness check |
| `GET /runs` | Basic | Lists available run dates from `output/logs/` |
| `GET /exceptions/queue/{priority}/{run_date}` | Basic | Returns priority queue JSON for a given date |
| `GET /briefing/{run_date}` | Basic | Returns morning briefing markdown for a given date |
| `POST /pipeline/trigger` | Basic | Triggers full pipeline run asynchronously via `BackgroundTasks`; returns a `run_id` |
| `GET /pipeline/status/{run_id}` | Basic | Reports the status (`queued`/`running`/`completed`/`failed`) of a background pipeline run from the in-memory run registry |

### Phase 12 API Surface
| Endpoint | Auth | Description |
|---|---|---|
| `POST /overrides` | Basic | Submits a new analyst override for pending planner review |
| `GET /overrides/pending` | Basic | Lists overrides awaiting planner approval |
| `GET /overrides/stats` | Basic | Aggregate override counts (total, by status, by override priority) for the active-learning stats strip |
| `POST /overrides/{override_id}/approve` | Basic, planner-only | Approves a pending override |
| `POST /overrides/{override_id}/reject` | Basic, planner-only | Rejects a pending override |

### Phase 13 API Surface
| Endpoint | Auth | Description |
|---|---|---|
| `GET /me` | Basic | Returns the authenticated username and resolved actor role for the current session |
| `GET /settings` | Basic | Returns safe runtime configuration for the Settings page, including provider/model, tuning knobs, env overrides, and user-role mappings (role map only exposed to planners) |
| `PATCH /settings` | Basic, planner-only | Applies a validated partial `.env` update and records a `SETTINGS_CHANGE` audit action |
| `POST /settings/validate-model` | Basic, planner-only | Validates a draft provider/model combination against the provider's live model list |
| `GET /models` | Basic | Queries the active provider for available model IDs and reports whether the current `AGENT_MODEL` is valid |
| `POST /actions` | Basic | Creates an execution request, injects the authenticated username, persists the action record, and attempts adapter execution |
| `GET /actions` | Basic | Paginated, filterable (status/action_type/run_date) list of actions across all exceptions, backing the Action History page |
| `GET /actions/{exception_id}` | Basic | Returns action records for a specific exception card, newest first |
| `POST /actions/{request_id}/retry` | Basic | Retries a previously failed action request using the stored payload and metadata |

### Current Open Work
- Finish the remaining Phase 13 scope beyond the execution MVP:
  - broader ERP-specific adapters beyond the generic/Slack adapter boundary
  - fuller role matrix / deeper RBAC beyond the current planner/analyst gates
- Complete the remaining launch-readiness operational checks:
  - manual browser click-through of dashboard, override flow, planner review, Action History page, and Phase 13 actions
  - confirm production role mappings and deployment credentials (`API_USERS`)

## Typical Data Scenarios
The agent must correctly handle these edge cases:
- **CRITICAL Scenario:** OOS + Tier 1 store + active TPR + nearby competitor.
- **Phantom Inventory:** OOS at Store but vendor fill rate is 97% and DC has 35 days remaining.
- **Vendor Pattern:** Multiple low-priority exceptions aggregating underneath a single struggling vendor.

---

## Claude Code Skills

When working in this project with **Claude Code**, the following skills are active via `.claude/settings.json`. Invoke them with the `Skill` tool before relevant tasks:

| Skill | Trigger |
|---|---|
| `superpowers:brainstorming` | Before any new feature or architecture change |
| `superpowers:writing-plans` | Before multi-step implementation tasks |
| `superpowers:executing-plans` | When executing a written plan |
| `superpowers:systematic-debugging` | When encountering any bug or test failure |
| `superpowers:test-driven-development` | Before writing implementation code |
| `superpowers:requesting-code-review` | Before merging or after major changes |
| `superpowers:verification-before-completion` | Before claiming work is done |
| `ralph-loop:ralph-loop` | To start an autonomous development loop (`ralph --monitor`) |
| `commit-commands:commit` | When committing changes |
| `commit-commands:commit-push-pr` | When pushing and opening a PR |
| `feature-dev:feature-dev` | When implementing a new feature end-to-end |
| `octo:debug` | Deep debugging workflows |
| `octo:tdd` | Test-driven development cycles |
| `octo:review` | Code review |
| `security-guidance:security-review` | Security audit before shipping |
| `claude-mem:make-plan` | Create a phased implementation plan |
| `claude-mem:mem-search` | Search cross-session memory for prior work |
