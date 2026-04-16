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

## Future Web UI (Agentic Copilot)
The system is migrating from a CLI batch process to a Web UI Copilot.
- **Phase 11:** MVP Command Center (Interactive queue viewing via FastAPI & Next.js)
- **Phase 12:** Active Learning (Overrides & "Suggested Learnings" stored in SQLite/PostgreSQL)
- **Phase 13:** Agentic Engagement (Native webhook buttons syncing back to the ERP)

## Typical Data Scenarios
The agent must correctly handle these edge cases:
- **CRITICAL Scenario:** OOS + Tier 1 store + active TPR + nearby competitor.
- **Phantom Inventory:** OOS at Store but vendor fill rate is 97% and DC has 35 days remaining.
- **Vendor Pattern:** Multiple low-priority exceptions aggregating underneath a single struggling vendor.
