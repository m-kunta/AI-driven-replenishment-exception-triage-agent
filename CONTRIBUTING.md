# Contributing Guide

Thanks for contributing to the Replenishment Exception Triage Agent.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_data.py
```

## Recommended Workflow

1. Pick a scoped task from `REPLENISHMENT_TRIAGE_AGENT_PROMPT.md`.
2. Implement in small, reviewable commits.
3. Add or update tests for behavior changes.
4. Run the relevant test suite locally.
5. Update docs (`README.md`, this file, or module docstrings) if contracts/status changed.

## Testing Expectations

Run at minimum:

```bash
pytest tests/test_ingestion.py -v
pytest tests/test_enrichment.py -v
```

If your changes affect shared models or utilities, run:

```bash
pytest tests/ -v
```

## Coding Standards

- Use Python 3.9+ compatible syntax.
- Prefer explicit type hints on public functions and methods.
- Raise typed exceptions from `src/utils/exceptions.py`.
- Keep ingestion adapters returning raw dictionaries; perform normalization/coercion in the normalizer.
- Preserve deterministic behavior for sample data generation (`seed=42`).

## Documentation Standards

- Keep implementation status accurate (avoid documenting planned scripts/features as available).
- Document config changes in `config/config.yaml` comments and README sections.
- Add concise docstrings for new public classes/functions.

## Pull Request Checklist

- [ ] Scope is focused and clearly described.
- [ ] Tests added/updated for the changed behavior.
- [ ] `pytest` passes for affected modules.
- [ ] Documentation updated for user-visible or developer-visible changes.
- [ ] No secrets committed (`.env`, keys, credentials).

## Questions

If requirements are unclear, refer to:

- `README.md` for current status and runnable scope
- `REPLENISHMENT_TRIAGE_AGENT_PROMPT.md` for phased acceptance criteria
- `CLAUDE.md` for implementation patterns and project-specific context
