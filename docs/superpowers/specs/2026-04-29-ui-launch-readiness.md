# UI Launch Readiness Check

**Date:** 2026-04-29  
**Scope:** Web UI launch-readiness pass for the Command Center, planner review flow, and current Phase 13 action surface.

## Summary

The UI is functional and close to launch-ready for an internal pilot. Core backend and frontend flows are in place, the production build now completes successfully, and the backend plus proxy-backed frontend routes respond correctly in a local smoke pass.

The main remaining gap is not a code failure but an operational one: a final human click-through with a real browser session should still be completed before broader launch, especially for the override, planner review, and Phase 13 action flows.

## What Was Verified

### Automated Verification

- Backend regression:
  - `tests/test_api_actions.py`
  - `tests/test_action_service.py`
  - `tests/test_action_store.py`
  - `tests/test_api.py`
- Frontend regression:
  - `src/lib/api.test.ts`
  - `src/components/ActionModal.test.tsx`
  - `src/components/OverrideModal.test.tsx`
  - `src/components/ExceptionCard.test.tsx`
  - `src/app/planner-review/page.test.tsx`

### Production Build

- `cd frontend && npm run build`
- Result: passes after removing the build-time dependency on Google-hosted `Geist` fonts in `frontend/src/app/layout.tsx`

### Local Smoke Verification

Verified against an isolated local backend/frontend pairing to avoid stale local process conflicts:

- Backend `GET /health` returned `200`
- Backend `GET /me` returned `200` with resolved actor profile
- Frontend home page returned `200`
- Frontend `/planner-review` returned `200`
- Frontend proxy `GET /api/proxy/me` returned `200` when wired to the isolated backend

## Issues Found And Resolved

### Build-Time Font Dependency

The frontend production build originally failed because `next/font/google` attempted to fetch `Geist` and `Geist Mono` during build. This created an unnecessary external dependency for production builds and failed in restricted environments.

Resolution:

- Removed the Google font import from `frontend/src/app/layout.tsx`
- Relied on the existing local CSS font stack in `frontend/src/app/globals.css`

### Local Startup Friction

`scripts/dev.sh` correctly refuses to start if `.env` still contains the placeholder `API_PASSWORD=changeme`. This is desirable behavior, but it means a fresh local smoke pass requires real local credentials first.

## Remaining Pre-Launch Checks

These are the remaining items before calling the UI fully launch-ready beyond an internal pilot:

1. Set a real `API_PASSWORD` in local and target deployment environments.
2. Perform a manual browser click-through of:
   - Command Center queue and briefing
   - analyst override submission
   - planner review approve/reject flow
   - Phase 13 action submission and retry
3. Confirm the intended role mappings for real users in `API_USER_ROLES` or the production-equivalent configuration.
4. Decide whether current Phase 13 planner-only gating is sufficient for launch, or whether a broader action-role matrix is required first.

## Recommendation

The UI is ready for an internal pilot or controlled rollout once the manual click-through is completed in a real browser and deployment credentials are configured. A broader production launch should wait until that manual validation is complete and the desired user-role mapping is confirmed.
