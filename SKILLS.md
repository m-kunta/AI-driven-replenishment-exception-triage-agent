# SKILLS.md — Agent & Developer Skill Index

This document defines the specific operational skills (playbooks) available in this repository, mapping exactly **what** the skill is, and **when** to use it. Reference this before taking action to ensure you use the correct pipeline path.

---

## 🧰 Skill Index

| Skill Name | What it does | WHEN to use it |
|------------|--------------|----------------|
| **`run_tests`** | Executes the full `pytest` suite | **BEFORE** completing a task, or **AFTER** refactoring any of the 4 core pipeline Layers. |
| **`triage_dry_run`** | Runs ingestion + enrichment only (`--dry-run`) | **WHEN** you need to verify data schemas, CSV structures, or enrichment logic WITHOUT incurring LLM API costs. |
| **`triage_full_run`** | Runs the full pipeline locally | **WHEN** you have modified a prompt in `prompts/` and need to test output logic, but use `--no-alerts` to avoid blasting webhooks. |
| **`grade_backtest`** | Executes `scripts/run_backtest.py` | **WHEN** you need to dynamically evaluate precision/recall after modifying the `triage_agent.py` logic. |
| **`add_enrichment`** | Pipeline for adding new data sources | **WHEN** the user asks to integrate a new signal (e.g. Weather API). You must touch `data_loader.py`, `engine.py`, and `models.py`. |
| **`tune_prompt`** | Modifies the AI's heuristic behavior | **WHEN** the AI priorities hallucinate. Do not edit `.py` code; you must teach via `prompts/few_shot_library.json`. |
| **`build_ui_view`** | Scaffolds Next.js/FastAPI components | **WHEN** extending the UI. You must keep Next.js contained in `/frontend/` and FastAPI in `src/api/`. |

---

## 📜 Execution Playbooks

*(Below are the explicit terminal commands to execute the skills above)*

### `run_tests`
```bash
# Python pipeline tests
.venv/bin/python3 -m pytest tests/ -v

# Frontend tests (run from frontend/ dir)
cd frontend && npm test
```

### `triage_dry_run`
```bash
.venv/bin/python scripts/run_triage.py --sample --dry-run
```

### `triage_full_run`
```bash
.venv/bin/python scripts/run_triage.py --sample --no-alerts --verbose
```

### `grade_backtest`
```bash
.venv/bin/python scripts/run_backtest.py --date <YYYY-MM-DD> --week 4 --sample
```

### `add_enrichment`
Touch these three files in order:
1. `src/enrichment/data_loader.py` — add loader function for the new data source
2. `src/enrichment/engine.py` — join the new signal into `EnrichedExceptionSchema`
3. `src/models.py` — add the new field(s) to `EnrichedExceptionSchema` and `TriageResult`

Then run `run_tests` to verify no schema regressions.

### `tune_prompt`
```bash
# Review current few-shot examples
cat prompts/few_shot_library.json

# Edit examples to correct hallucinating behaviour — do NOT touch .py files
# Then verify with a dry run:
.venv/bin/python scripts/run_triage.py --sample --no-alerts --verbose
```

### `build_ui_view`
```bash
# Backend: add new endpoint to src/api/app.py, then verify
.venv/bin/python3 -m pytest tests/test_api.py -v

# Frontend: add component under frontend/src/components/, page under frontend/src/app/
# Then verify
cd frontend && npm test

# Start both servers to test end-to-end
uvicorn src.api.app:app --reload --port 8000 &
cd frontend && npm run dev
```

---

## 🧩 FULL-STACK UI DEVELOPMENT SKILLS (PHASE 11+)

When transitioning into the Web UI build architecture (FastAPI + Next.js), adhere strictly to these operational constraints:

### Backend Extensions (FastAPI) — Phase 11
- **Do not rewrite existing Pytest coverage:** The FastAPI shell (`src/api/app.py`) must cleanly *import* from `src.main` without modifying the core functional boundaries of Layers 1 through 4.
- **Use sync `def` endpoints:** The pipeline is CPU-bound/blocking — `async def` is not appropriate. Long-running pipeline calls must use `BackgroundTasks` to avoid blocking the server.
- **Auth on every non-health endpoint:** All endpoints except `/health` must use `Depends(get_current_username)`. `API_PASSWORD` must raise `RuntimeError` if unset — no silent defaults.
- **`output/logs/` is the source of truth** for triage results. The API reads these files; it does not write to them.

### Frontend Enhancements (Next.js) — Phase 11
- **Monorepo Awareness:** Always scaffold Next.js tightly into a root `./frontend/` folder. All dependencies must be strictly scoped to `frontend/package.json`. Never install JS packages at the project root.
- **Environment variables:** Frontend credentials live in `frontend/.env.local` (copy from `.env.local.example`). Use `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_USERNAME`, `NEXT_PUBLIC_API_PASSWORD`.
- **Styling:** Use TailwindCSS v4. Global utility classes (`.glass`, `.glass-hover`, `transition-all-smooth`) live in `frontend/src/app/globals.css` — use them before inventing new ones. Keep components modular in `frontend/src/components/`.
- **Shadcn/UI is deferred to Phase 12+** — do not install it for Phase 11 work.

### Database Rules — Phase 12 (not yet implemented)
- Utilize SQLite via `SQLAlchemy ORM` for UI state toggling (Acknowledging/Resolving/Dismissing exceptions). Do not implement this in Phase 11 — `output/logs/` files are the sole source of truth until Phase 12.

---

## 🚦 AI ENGAGEMENT & REASONING RULES

When an AI Agent is working on this repo, observe these epistemic constraints:

1. **Be Data-Safe:** Never run commands that truncate databases or overwrite `data/sample/` without explicit permission.
2. **Don't Assume Dependencies:** Always check `requirements.txt` via `cat` or `grep` before importing a new library. If you need a new dependency, add it to `requirements.txt` and request user permission to pip install. Pydantic v2 patterns apply. For frontend deps, check `frontend/package.json` first.
3. **Respect Immutability Warnings:** The Triage Agent layer uses mutable objects (`TriageResult` fields are updated by phantom webhooks and pattern analyzers). Preserve this explicit mutability pattern during refactoring.
4. **Loguru Standards:** No raw `print()` statements. Always use `from loguru import logger` and route outputs via structured `logger.info()` or `logger.warning()`. Use lazy format: `logger.error("msg: {}", e)` — never f-strings inside logger calls.
5. **Frontend Environment Setup:** The Next.js frontend requires `frontend/.env.local` before `npm run dev` will connect to the backend. Copy `frontend/.env.local.example` and set `NEXT_PUBLIC_API_PASSWORD` to match the backend's `API_PASSWORD` env var. Without this, all API calls will return 401.
