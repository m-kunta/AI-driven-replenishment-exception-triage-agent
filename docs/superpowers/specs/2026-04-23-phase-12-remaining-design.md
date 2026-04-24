# Phase 12 Remaining Design

**Date:** 2026-04-23  
**Phase:** 12 — Active Learning  
**Scope:** Complete the remaining Phase 12 work by splitting delivery into `12a` analyst-facing override submission and `12b` planner approval, while finishing the backend few-shot learning loop.

## Goal

Phase 12 already has the database layer and FastAPI endpoints for override submission and approval. The remaining work is to:

1. Add an analyst-facing inline override workflow to the Command Center.
2. Add a separate planner review screen/tab for pending override decisions.
3. Connect approved overrides into prompt composition so the triage pipeline can learn from accepted corrections.
4. Run auto-approval at pipeline startup so stale pending overrides can enter the approved pool without manual intervention.

## Delivery Split

## Rollout Strategy

The remaining Phase 12 work should be executed as three separate sessions or days.

### Session 1 — 12a Analyst Override Submission

Focus on the analyst-facing frontend MVP.

- build the override modal and full-field form,
- add the inline override entry point from `ExceptionCard`,
- wire the frontend client to `POST /overrides` through the proxy,
- add focused frontend tests for the modal and submission flow.

### Session 2 — 12b Planner Approval

Focus on the planner-facing dashboard workflow.

- add a separate planner review screen/tab,
- wire the frontend client to pending/approve/reject endpoints,
- build the pending-review UI and rejection reason flow,
- add focused frontend tests for planner review behavior.

### Session 3 — Backend Learning Loop And Integration

Focus on closing the Active Learning loop.

- update prompt composition to consume approved overrides,
- run `auto_approve_pending()` at pipeline startup,
- add backend unit and integration tests proving the full lifecycle.

### 12a — Analyst Override Submission

`12a` delivers the analyst-facing UI only.

- Add an inline `Override` action to each exception card.
- Open a modal from the card rather than routing to a separate page.
- Expose all overrideable fields in the first pass:
  - `override_priority`
  - `override_root_cause`
  - `override_recommended_action`
  - `override_financial_impact_statement`
  - `override_planner_brief`
  - `override_compounding_risks`
  - `analyst_note`
- Submit to the existing `POST /overrides` API through the Next.js BFF proxy.
- Include the enriched exception snapshot required by the backend.

### 12b — Planner Approval

`12b` delivers the planner-facing review workflow in a separate dashboard destination.

- Add a separate screen/tab for pending override review.
- Fetch pending records from `GET /overrides/pending`.
- Render the original exception context alongside the proposed override values.
- Support `Approve` and `Reject` actions.
- Require only an optional rejection reason, matching the current backend contract.
- Remove approved/rejected items from the pending list after successful action completion.

## Recommended Architecture

Use one shared override domain model in the frontend with two UI entry points.

- Shared frontend types and payload mappers live in `frontend/src/lib/api.ts` and related local helpers.
- `12a` uses the shared model inside an exception-card modal.
- `12b` uses the same model in a planner review screen/tab.
- Existing FastAPI endpoints remain the backend source of truth.

This keeps field names, validation rules, and payload shapes aligned across analyst and planner workflows without introducing a larger state-management refactor.

## UI Design

### 12a Analyst Flow

The current dashboard in `frontend/src/app/page.tsx` remains the home for analysts.

- Each `ExceptionCard` gets an `Override` button.
- Clicking it opens a modal anchored in the existing dashboard flow.
- The modal is prefilled from the current `TriageResult` where sensible to represent the LLM's original output.
- Analysts can edit any subset of supported override fields.
- Submission sends the immutable snapshot plus the complete set of overrideable fields (representing the final correct state, unmodified fields just pass through the prefilled values).
- On success:
  - close the modal,
  - show a lightweight success confirmation,
  - leave the exception card in place.
- On failure:
  - keep the modal open,
  - show an inline error,
  - allow retry without losing user input.

### 12b Planner Flow

Planner review should be separate from the analyst’s queue view.

- Add a dedicated planner tab/screen reachable from the dashboard.
- The screen lists pending overrides in oldest-first order, consistent with the API. A reasonable limit (e.g., first 50) or pagination should be considered to handle scale.
- Each row/card shows:
  - exception identifier and run date,
  - analyst username and submission timestamp,
  - the original enriched input snapshot,
  - the proposed override fields,
  - analyst note when present.
- `Approve` performs the existing approval call.
- `Reject` opens a small inline reason entry state or modal, then calls the reject endpoint.
- On success, the reviewed item disappears from the pending list without a full reload if possible.
- On failure, the item remains visible and shows a local error state.
- **Concurrency:** Ensure the backend handles idempotency gracefully (e.g., if two planners approve the same item simultaneously, the second attempt should not crash but cleanly remove the item from their view).

## Backend Learning Loop

The remaining backend work completes the Active Learning cycle.

### Prompt Composition

`src/agent/prompt_composer.py` currently uses only static examples from `prompts/few_shot_library.json`.

It should be extended to support approved override examples from `OverrideStore`:

- load approved override examples, limiting to a sensible cap (e.g., the 3-5 most recent or relevant examples) to prevent blowing up the LLM token context,
- format them into the same prompt section,
- fall back to static few-shot examples when no approved examples exist.

The preferred behavior is:

1. Use a capped subset of approved override examples when available.
2. Fall back to static examples when none are approved.

This keeps the prompt predictable and avoids inflating the system prompt unnecessarily.

### Pipeline Startup Auto-Approval

`src/main.py` should call `auto_approve_pending()` before constructing the agent/prompt path for a pipeline run.

This ensures:

- pending overrides older than one day are promoted at run start,
- newly approved rows are immediately eligible for prompt composition during that same run,
- the TTL rule described in the Phase 12 schema spec is actually operationalized.

*Note: Tying auto-approval to pipeline startup is a pragmatic MVP approach to guarantee fresh data before a run. However, if the pipeline runs infrequently, pending overrides may sit longer than 24 hours. A scheduled background task (cron job) would be the long-term solution to strictly enforce the TTL.*

## Data Contracts

### Frontend Submission Payload

The submission payload should match the existing backend request model:

```json
{
  "exception_id": "EXC-001",
  "run_date": "2026-04-23",
  "enriched_input_snapshot": { "...": "..." },
  "override_priority": "HIGH",
  "override_root_cause": "Possible phantom inventory mismatch",
  "override_recommended_action": "Confirm on-hand balance before expediting",
  "override_financial_impact_statement": "Risk is lower than model estimated due to healthy DC position.",
  "override_planner_brief": "Check store count accuracy and defer rush order.",
  "override_compounding_risks": ["POTENTIAL_PHANTOM_INVENTORY"],
  "analyst_note": "Vendor service is healthy; likely inventory integrity issue."
}
```

### Frontend Review Data

The planner review screen should treat `GET /overrides/pending` as the canonical pending-review shape and not reconstruct values from queue files.

## Error Handling

### Analyst Submission

- Validate obvious client-side issues before submit where helpful.
- Do not rely on client validation alone; backend validation remains authoritative.
- Disable the submit action while the request is in flight.
- Preserve user-entered form state on API failure.
- Show API errors inline inside the modal.

### Planner Approval

- Disable action buttons while approve/reject is in flight.
- Remove an item from the list only after the API confirms success.
- Restore controls and show an inline error on failure.
- Preserve the rejection reason input if the reject request fails.

### Learning Loop

- If the override database is empty or returns no approved examples, prompt composition must still succeed using static examples.
- If auto-approval promotes zero rows, pipeline execution should continue normally.

## Permissions Assumption

This design does not introduce role-based access control.

- Any authenticated user can reach the analyst submission UI.
- Any authenticated user can reach the planner review screen.

If role separation becomes necessary later, it should be treated as a separate access-control phase rather than folded into the remaining Phase 12 work.

## Testing Strategy

### Frontend Tests

Add targeted tests for:

- opening and closing the override modal,
- prefilled form values from a `TriageResult`,
- editing all supported override fields,
- submission payload shape,
- success and failure states for submission,
- planner screen rendering from pending override data,
- approve flow,
- reject flow with optional reason,
- local error handling on failed planner actions.

### API Tests

Add or extend API tests for:

- pending override response shape stability,
- approval and rejection behavior under expected edge cases,
- any backend validation cases exposed by the new UI.

### Backend Tests

Add tests covering:

- `auto_approve_pending()` invocation during pipeline startup,
- prompt composer fallback to static examples,
- prompt composer use of approved override examples when present.

### Integration Slice

Add one small lifecycle test proving:

1. an override is stored as pending,
2. it becomes approved through explicit approval or TTL promotion,
3. the next prompt composition includes it as a learning example.

## File Impact

Expected touch points:

- `frontend/src/app/page.tsx`
- `frontend/src/components/ExceptionCard.tsx`
- new modal/review components under `frontend/src/components/`
- `frontend/src/lib/api.ts`
- `frontend/src/app/` route or tab wiring for planner review
- `src/agent/prompt_composer.py`
- `src/main.py`
- `tests/test_api.py`
- `tests/test_db_store.py`
- `tests/test_prompt_composer.py`
- frontend component and API client tests

## Out Of Scope

The following are not part of this remaining Phase 12 design:

- ERP write-back actions from the UI,
- role-based auth or planner-only permissioning,
- redesign of the existing Command Center layout,
- a separate deep-edit exception detail page,
- broader workflow orchestration beyond override submission and approval.

## Success Criteria

Phase 12 remaining work is complete when:

1. Analysts can submit full-field overrides inline from exception cards.
2. Planners can review pending overrides in a separate screen/tab and approve or reject them.
3. Approved overrides are available to prompt composition as few-shot examples.
4. Pending overrides older than one day are auto-approved at pipeline startup.
5. The new UI flows and backend learning loop are covered by automated tests.
