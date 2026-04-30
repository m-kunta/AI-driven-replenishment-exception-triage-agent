# CLAUDE.md — Developer Context & Technical Rules

This document provides necessary technical constraints, stack information, and structural mapping for AI coding assistants working in the **Replenishment Exception Triage Agent** repository.

## Project Structure
```
src/
├── models.py                  # Pydantic schemas (CanonicalException, EnrichedExceptionSchema, TriageResult)
├── ingestion/                 # Layer 1: Adapters & normalizer.py
├── enrichment/                # Layer 2: data_loader.py + engine.py
├── agent/                     # Layer 3: Reasoning Engine (llm_provider, prompt_composer, triage_agent)
├── output/                    # Layer 4: router, dispatcher, logger, briefing
├── actions/                   # [Phase 13] Action service + adapter boundary
├── db/action_store.py         # [Phase 13] SQLite-backed action audit persistence
└── api/                       # [Phase 11+] FastAPI interface layer for the Web UI and action APIs
config/
└── config.yaml                # Core config w/ env variable injection
prompts/                       # Markdown blocks and JSON few-shot examples
data/                          # Sample datasets and SQL schemas
scripts/                       # CLI interaction scripts (run_triage, run_backtest)
frontend/                      # [Phase 11] Next.js Web UI — start with `bash scripts/dev.sh` (sources root .env)
└── src/app/api/proxy/         # BFF proxy — injects Basic Auth server-side; credentials never reach the browser
```

## Current Delivery Status
- **Phase 11 — MVP Command Center:** Complete.
- **Phase 12 — Active Learning:** Complete.
- **Phase 13 — Agentic Engagement:** In progress. The first execution slice is live with action modal submission, inline action history/status, FastAPI action endpoints, retry support, planner-only gating for `STORE_CHECK` / `VENDOR_FOLLOW_UP`, and per-user role resolution through backend-authenticated actor profiles.

## Tech Stack & Architecture Constraints
- **Language:** Python 3.9+ (`from __future__ import annotations` required).
- **Core Libraries:** `pydantic v2` (for all data moving between layers), `loguru` (for all print statements).
- **Multi-Provider LLM Config:** 
  You must never hardcode Anthropic specific API calls. Utilize `get_provider(config.agent)`.
  Available configured providers: `claude`, `openai`, `gemini`, `ollama`.
  Auth flows via `.env`.

## Implementation Rules
1. **Adapters:** Base adapters must always return `List[Dict]`.
2. **Immutability Waiver:** `TriageResult` is highly mutable by design. `phantom_webhook` and `pattern_analyzer` modify `.priority` and `.escalated_from` after LLM parsing.
3. **Context Carry-Forward:** The system joins heavy contextual variables in Layer 2. `batch_processor` carries these forward onto `TriageResult` explicitly to avoid output layer re-joins.
4. **Error Handling:** Use custom exceptions from `utils/exceptions.py`. The pipeline must continue processing remaining batches if a single batch fails to parse.
5. **Monorepo Strictness:** Next.js must strictly stay inside `frontend/`. Python FastAPI stays inside `src/api/`. Do not bleed JS code into Python dirs.

## API Layer Rules (src/api/)
- All endpoints must use `Depends(get_current_username)` for auth — no unauthenticated write endpoints.
- `API_PASSWORD` must raise `RuntimeError` if unset — no silent fallback defaults permitted.
- Pipeline/file endpoints may remain sync `def`, but action execution endpoints may use `async def` because they call adapter-driven async service methods.
- Loguru lazy format only: `logger.error("msg: {}", e)` — no f-strings in any logger call.
- Phase 13 auth rules: `POST /actions` must inject `requested_by` and resolve `requested_by_role` server-side from the authenticated username. Never trust browser-supplied actor metadata.
- `GET /me` is the source of truth for the frontend's current actor profile. Do not reintroduce build-time role flags as the active UI permission source.
- New general API endpoints belong in `tests/test_api.py`; Phase 13 action endpoints and role-gating coverage live in `tests/test_api_actions.py`.

## Frontend Proxy Rules (frontend/src/app/api/proxy/)
- `API_USERNAME`, `API_PASSWORD`, and `API_URL` are **server-side only** — read by the BFF proxy in `frontend/src/app/api/proxy/[...path]/route.ts`.
- **Never** add these to `NEXT_PUBLIC_*` or the `env` block in `next.config.ts`. Doing so leaks credentials into the browser JS bundle.
- All browser fetch calls must target `/api/proxy/...` — never call the FastAPI backend directly from client code.
- No `frontend/.env.local` is needed or used; credentials come from the root `.env` via `bash scripts/dev.sh`.

## Basic Execution Paths
- **Format Code:** Use `ruff` or standardized `.venv` wrappers.
- **Run Python Tests:** `.venv/bin/python3 -m pytest tests/ -v`
- **Run Frontend Tests:** `cd frontend && npm test`
- **CLI Executions:** Always utilize `scripts/run_triage.py` or `scripts/run_backtest.py`. Do not invoke `main.py` directly.
