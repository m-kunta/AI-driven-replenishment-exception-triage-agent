# Phase 12c Backend Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Active Learning backend loop so approved overrides are eligible for prompt composition and stale pending overrides are auto-approved at pipeline startup.

**Architecture:** Inject `OverrideStore` into prompt composition in a small, testable way and keep static few-shot examples as the fallback path. Trigger `auto_approve_pending()` in `run_triage_pipeline()` before the agent/prompt path is built, then prove the lifecycle with unit and integration tests.

**Tech Stack:** Python 3.9+, pytest, sqlite3, pydantic v2

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `src/agent/prompt_composer.py` | Approved-override few-shot support |
| Modify | `src/main.py` | Pipeline startup auto-approval hook |
| Modify | `tests/test_prompt_composer.py` | Prompt composer override tests |
| Modify | `tests/test_main.py` | Auto-approve startup tests |

## Task 1: Add PromptComposer Support For Approved Override Examples

**Files:**
- Modify: `src/agent/prompt_composer.py`
- Modify: `tests/test_prompt_composer.py`

- [ ] **Step 1: Write the failing prompt-composer tests**

Add tests like:

```python
def test_uses_override_store_examples_when_present(prompts_dir: Path):
    store = MagicMock()
    store.get_approved_few_shot_examples.return_value = [
        {
            "input": {"exception_id": "override-001"},
            "output": {"priority": "CRITICAL", "root_cause": "Planner corrected"},
        }
    ]
    composer = PromptComposer(prompts_dir=prompts_dir, override_store=store)
    system = composer.compose_system_prompt()
    assert "override-001" in system
    assert "Planner corrected" in system

def test_falls_back_to_static_few_shots_when_override_store_empty(prompts_dir: Path):
    store = MagicMock()
    store.get_approved_few_shot_examples.return_value = []
    composer = PromptComposer(prompts_dir=prompts_dir, override_store=store)
    system = composer.compose_system_prompt()
    assert "Test example" in system
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python3 -m pytest tests/test_prompt_composer.py -q
```

Expected: FAIL because `PromptComposer` does not accept `override_store`.

- [ ] **Step 3: Implement the minimal override-store integration**

Update `PromptComposer.__init__`:

```python
def __init__(
    self,
    prompts_dir: Path = PROMPTS_DIR,
    override_store: Optional[OverrideStore] = None,
    override_limit: int = 10,
) -> None:
```

Add helper methods:

```python
def _get_few_shot_examples(self) -> list[dict]:
    if self._override_store is not None:
        examples = self._override_store.get_approved_few_shot_examples(limit=self._override_limit)
        if examples:
            return examples
    static = json.loads(self._cache["few_shot_library.json"])
    return [
        {"input": ex["exception"], "output": ex["correct_output"], "description": ex["description"]}
        for ex in static
    ]
```

Then adapt `_format_few_shots()` to accept either shape while preserving the `## Few-Shot Examples` section header.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
.venv/bin/python3 -m pytest tests/test_prompt_composer.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/prompt_composer.py tests/test_prompt_composer.py
git commit -m "feat: load approved override examples in prompt composer"
```

## Task 2: Trigger Auto-Approval At Pipeline Startup

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing main-pipeline test**

Add to `tests/test_main.py`:

```python
def test_auto_approve_pending_called_before_triage_agent():
    run_result = _make_run_result()
    mock_store = MagicMock()

    with (
        patch("src.main.validate_required_env_vars"),
        patch("src.main.OverrideStore", return_value=mock_store),
        patch("src.main.TriageAgent") as MockAgent,
        patch("src.main.AlertDispatcher"),
        patch("src.main.BriefingGenerator") as MockBriefing,
        patch("src.main.ExceptionLogger") as MockLogger,
    ):
        MockAgent.return_value.run.return_value = run_result
        MockBriefing.return_value.generate.return_value = Path("output/briefings/b.md")
        MockLogger.return_value.log.return_value = Path("output/logs/exception_log.csv")
        from src.main import run_triage_pipeline
        run_triage_pipeline(config_path=_SAMPLE_CONFIG, no_alerts=True, sample=True)

    mock_store.auto_approve_pending.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python3 -m pytest tests/test_main.py -q
```

Expected: FAIL because `src.main` does not create or call `OverrideStore`.

- [ ] **Step 3: Implement the startup hook**

In `src/main.py`:

```python
from src.db.store import OverrideStore
```

Then before `TriageAgent(config)`:

```python
override_store = OverrideStore()
promoted = override_store.auto_approve_pending()
logger.info("Auto-approved {} pending overrides at startup", promoted)
```

If `TriageAgent` or `PromptComposer` needs the store, thread it through as part of this same change rather than instantiating a second store deeper in the call stack.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
.venv/bin/python3 -m pytest tests/test_main.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: auto-approve pending overrides at pipeline startup"
```

## Task 3: Add Lifecycle Coverage

**Files:**
- Modify: `tests/test_prompt_composer.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing lifecycle test**

Add one integration-style test using a real in-memory `OverrideStore`:

```python
def test_approved_override_enters_prompt_examples(tmp_path: Path, prompts_dir: Path):
    from src.db.store import OverrideStore
    store = OverrideStore(":memory:")
    row_id = store.insert_override(
        exception_id="EXC-001",
        run_date="2026-04-23",
        analyst_username="analyst1",
        enriched_input_snapshot={"exception_id": "EXC-001"},
        override_priority="HIGH",
        analyst_note="Planner note",
    )
    store.approve_override(row_id, "planner1")
    composer = PromptComposer(prompts_dir=prompts_dir, override_store=store)
    system = composer.compose_system_prompt()
    assert "EXC-001" in system
    assert "Planner note" in system
```

- [ ] **Step 2: Run the targeted tests to verify the new test fails**

Run:

```bash
.venv/bin/python3 -m pytest tests/test_prompt_composer.py tests/test_main.py -q
```

Expected: FAIL until the full shape/formatting path is correct.

- [ ] **Step 3: Adjust formatting and startup wiring minimally**

Make the smallest code changes necessary so:

- approved override examples serialize cleanly into the few-shot block,
- the prompt still includes static examples when the store is empty,
- pipeline startup auto-approval does not change dry-run and no-alerts semantics.

- [ ] **Step 4: Run the full targeted backend suite**

Run:

```bash
.venv/bin/python3 -m pytest tests/test_db_store.py tests/test_prompt_composer.py tests/test_main.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_composer.py tests/test_main.py src/agent/prompt_composer.py src/main.py
git commit -m "test: cover override approval learning loop lifecycle"
```

## Self-Review

- Spec coverage: covers prompt integration, startup auto-approval, fallback behavior, and lifecycle verification.
- Placeholder scan: no unresolved placeholders remain.
- Type consistency: `OverrideStore.get_approved_few_shot_examples(limit=...)` matches the existing store API.
