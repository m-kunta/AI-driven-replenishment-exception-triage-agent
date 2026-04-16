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
.venv/bin/python3 -m pytest tests/ -v
```

### `triage_dry_run`
```bash
python scripts/run_triage.py --sample --dry-run
```

### `triage_full_run`
```bash
python scripts/run_triage.py --sample --no-alerts --verbose
```

### `grade_backtest`
```bash
python scripts/run_backtest.py --date <YYYY-MM-DD> --week 4 --sample
```

---

## 🧩 FULL-STACK UI DEVELOPMENT SKILLS (PHASE 11+)

When transitioning into the Web UI build architecture (FastAPI + Next.js), adhere strictly to these operational constraints:

### Backend Extensions (FastAPI)
- **Do not rewrite existing Pytest coverage:** The FastAPI shell (`src/api/app.py`) must cleanly *import* from `src.main` without modifying the core functional boundaries of Layers 1 through 4.
- **Asynchronous Flow:** FastAPI endpoints should primarily be `async def`. But because the core triage pipeline may be synchronous/blocking, wrap the pipeline executions utilizing `BackgroundTasks` to avoid freezing the UI.
- **Database Rules:** Utilize SQLite via `SQLAlchemy ORM` for UI state toggling (Acknowledging/Resolving tasks). `output/logs/` remain the source of truth for the scheduled runs.

### Frontend Enhancements (Next.js)
- **Monorepo Awareness:** Always scaffold Next.js tightly into a root `./frontend/` folder. All dependencies should be strictly scoped to `frontend/package.json`.
- **Styling:** Use `TailwindCSS` with `Shadcn/UI` exclusively. Avoid raw CSS files where possible. Keep components modular in `frontend/components/`.

---

## 🚦 AI ENGAGEMENT & REASONING RULES

When an AI Agent is working on this repo, observe these epistemic constraints:

1. **Be Data-Safe:** Never run commands that truncate databases or overwrite `data/sample/` without explicit permission.
2. **Don't Assume Dependencies:** Always check `requirements.txt` via `cat` or `grep` before importing a new library. If you need a new dependency, add it to `requirements.txt` and request user permission to pip install. Pydantic v2 patterns apply.
3. **Respect Immutability Warnings:** The Triage Agent layer uses mutable objects (`TriageResult` fields are updated by phantom webhooks and pattern analyzers). Preserve this explicit mutability pattern during refactoring.
4. **Loguru Standards:** No raw `print()` statements. Always use `from loguru import logger` and route outputs via structured `logger.info()` or `logger.warning()`.
