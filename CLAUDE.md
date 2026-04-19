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
└── api/                       # [Phase 11] FastAPI interface layer for the Web UI
config/
└── config.yaml                # Core config w/ env variable injection
prompts/                       # Markdown blocks and JSON few-shot examples
data/                          # Sample datasets and SQL schemas
scripts/                       # CLI interaction scripts (run_triage, run_backtest)
frontend/                      # [Phase 11] Next.js Web UI — copy frontend/.env.local.example → frontend/.env.local before running
```

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
- Use sync `def` endpoints — the pipeline is CPU-bound/blocking; `async def` is not appropriate here.
- Loguru lazy format only: `logger.error("msg: {}", e)` — no f-strings in any logger call.
- New endpoints must have corresponding tests in `tests/test_api.py` using the `_api_credentials` autouse fixture.

## Basic Execution Paths
- **Format Code:** Use `ruff` or standardized `.venv` wrappers.
- **Run Python Tests:** `.venv/bin/python3 -m pytest tests/ -v`
- **Run Frontend Tests:** `cd frontend && npm test`
- **CLI Executions:** Always utilize `scripts/run_triage.py` or `scripts/run_backtest.py`. Do not invoke `main.py` directly.
