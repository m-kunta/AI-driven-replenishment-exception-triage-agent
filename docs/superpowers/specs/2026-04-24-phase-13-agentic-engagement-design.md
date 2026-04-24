# Phase 13 Agentic Engagement Design

**Date:** 2026-04-24  
**Phase:** 13 — Agentic Engagement  
**Status:** Proposed  
**Scope:** Add manual user-triggered execution actions to the Command Center so planners and analysts can move from triage to operational follow-through through typed backend actions and outbound ERP/webhook adapters.

## Summary

Phase 12 completed the active learning loop: analysts can submit overrides, planners can approve or reject them, and approved examples now feed prompt composition. Phase 13 builds on that foundation by letting users take explicit downstream actions on an exception without leaving the Command Center.

The first Phase 13 slice is intentionally narrow:

- actions are always user-triggered, never autonomous,
- only a small catalog of action types is supported,
- execution happens through typed backend services rather than direct LLM output,
- inline execution state is visible on the exception card,
- full cross-run action history is deferred to a later phase.

## Goals

- Allow a planner or analyst to trigger a small set of operational actions from an exception card.
- Preserve a clean separation between AI recommendation and system execution.
- Add durable audit records for action requests and outcomes.
- Support retries for failed actions without creating duplicate downstream work.
- Prepare the data model for future role-based enforcement without making RBAC the core of this phase.

## Non-Goals

- Fully autonomous action execution.
- A generic workflow builder or rules engine.
- Broad ERP-specific connector coverage in v1.
- A dedicated action-history screen spanning all runs.
- Advanced retry orchestration, backoff policies, or distributed job coordination.

## Recommended Approach

Use a typed command workflow with explicit user confirmation.

The frontend adds action buttons or a compact action menu to each exception card. Selecting an action opens a lightweight confirmation modal for any action-specific fields. On submit, the UI sends a typed action request to a FastAPI endpoint. The backend validates the request, records it, hands it to an execution service, and routes it through an adapter boundary that can target a webhook or ERP integration.

This approach is preferred over direct webhook calls from the browser or a generalized automation framework because it keeps safety, audit, retries, and future RBAC in one place.

## Architecture

### Frontend

- Add action entry points to the exception card or a compact action menu.
- Open a confirmation modal with only the fields required by the chosen action type.
- Show durable inline state on the card after submission:
  - `queued`
  - `sent`
  - `failed`
  - `completed`
- Provide a retry or resubmit control for failed actions.

### API Layer

Add new action endpoints under the FastAPI app for:

- creating an action request,
- fetching current action state for an exception card if needed,
- retrying a failed action.

The API is the only layer allowed to accept execution requests from the UI.

### Application Service Layer

Introduce a typed action service that:

- validates the requested action against the supported action catalog,
- enriches the request with metadata such as requester identity and role,
- persists an action audit record,
- invokes the correct outbound adapter,
- updates execution state based on the adapter result.

### Integration Boundary

Adapters provide the interface to downstream operational systems. The v1 design should support at least a generic webhook adapter, with room for future ERP-specific adapters. The rest of the app should depend on the adapter interface, not on vendor-specific logic.

## Action Model

The first action catalog should stay intentionally small. Candidate actions:

- create or escalate a replenishment review,
- request inventory verification,
- request vendor follow-up,
- trigger a store or DC check,
- acknowledge and defer with a reason.

Each action request should include:

- `exception_id`
- `run_date`
- `action_type`
- `requested_by`
- `requested_by_role`
- `request_id` or equivalent idempotency key
- action-specific structured payload fields
- timestamps
- execution status
- downstream response metadata

## Idempotency

Phase 13 must account for double-clicks, browser resubmits, and network retries.

Preferred design:

- the client generates a `request_id` UUID when the action modal opens or submits,
- the backend treats that UUID as the idempotency key for the action request,
- repeated submissions with the same key return the same logical action record instead of executing a duplicate outbound action.

If the client UUID path cannot be used for some integrations, the backend may also enforce a secondary deduplication rule using a stable tuple such as:

- `exception_id`
- `run_date`
- `action_type`
- `requested_by`

## Roles And Permissions

Phase 13 should model role in the request and audit record from day one, even if strict RBAC enforcement is phased in later.

Each action request and stored record should include:

- `requested_by`
- `requested_by_role`

The action catalog should also define the intended actor type for each action so the system is ready for future enforcement. For example:

- analysts may be allowed to request verification-oriented actions,
- planners may be the only role allowed to escalate or trigger execution-heavy actions.

The backend validation seam should exist now so role enforcement can be tightened later without changing the data contract.

## UI Flow

1. User reviews a triaged exception in the Command Center.
2. User selects an available action.
3. A compact modal confirms the action and gathers any required fields.
4. The frontend submits the typed request with a client-generated idempotency key.
5. The card updates to inline execution state.
6. If execution fails, the card offers retry or resubmit rather than leaving a dead end.

## Audit Trail

Phase 13 includes durable audit recording for the lifecycle of each action:

- requested
- sent
- failed
- completed

The inline card state is part of the delivered scope. A dedicated cross-run action history page is explicitly deferred to Phase 14.

## Error Handling

- Invalid action payloads should fail validation clearly at the API boundary.
- Adapter failures should update the action to `failed` and preserve the failure reason.
- Retry should create no duplicate downstream action when the same idempotency key is reused.
- Frontend state should avoid optimistic success claims before the backend acknowledges the request.

## Testing

### Frontend

- action button or menu visibility,
- confirmation modal behavior,
- inline execution state transitions,
- failure state rendering,
- retry or resubmit behavior.

### Backend

- action request validation,
- role metadata persistence,
- idempotency behavior for duplicate submissions,
- adapter invocation and result handling,
- status transitions across `queued`, `sent`, `failed`, and `completed`.

### Integration

- end-to-end request flow through API -> action service -> adapter,
- duplicate submission returning the same logical request,
- failed action retrying cleanly,
- audit record updates across the action lifecycle.

## Delivery Recommendation

Deliver Phase 13 in a narrow first slice:

1. add one or two high-value action types,
2. support manual user-triggered execution only,
3. provide inline status plus retry,
4. log the full action lifecycle,
5. leave multi-system action history and stricter RBAC expansion for the next phase.

This keeps the scope aligned with the current product maturity while creating a strong foundation for deeper operational automation.
