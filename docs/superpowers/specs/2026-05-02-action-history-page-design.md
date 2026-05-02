# Action History Page Design

## Goal
Add a dedicated frontend page for cross-run downstream action history so planners and analysts can quickly audit prior actions, isolate failures, and retry failed requests without leaving the web UI.

## Scope
This design covers the frontend UI for the existing global actions API and client helpers:
- new Next.js route at `/actions`
- navigation entry from the Command Center
- audit-first table layout with filters and pagination
- inline retry affordance for failed actions
- loading, empty, and error states
- page-level frontend tests

Out of scope:
- backend API changes
- new action detail drill-down views
- cross-page shared component extraction beyond lightweight local helpers

## User Experience
The page should feel like an operational audit workspace rather than a second dashboard.

Structure:
- back link to the Command Center
- page title and one-sentence description
- compact filter toolbar
- full-width results table
- simple pagination controls at the bottom

Primary workflows:
1. Filter to `failed` actions and scan recent issues.
2. Narrow by `action_type` and `run_date` to investigate a specific operational slice.
3. Retry an eligible failed action and see the refreshed status on the same page.

## Layout And Behavior

### Header
- Include a back link to `/`.
- Title: `Action History`.
- Supporting text should explain that the page shows cross-run downstream execution history.

### Filter Toolbar
- Controls:
  - `status` dropdown
  - `action type` dropdown
  - `run date` dropdown or text/select control based on available run values already used elsewhere in the app
  - refresh button
- Supporting metadata:
  - compact result count such as `1-25 of 86`
- Behavior:
  - changing any filter resets `offset` to `0`
  - refresh preserves current filters and pagination
  - filter state is local page state; no URL sync in this pass

### Table
Columns:
- `Created`
- `Exception`
- `Run Date`
- `Action Type`
- `Status`
- `Requested By`
- `Quick Action`

Rendering notes:
- `Created` uses the same style of localized timestamp formatting already used elsewhere in the UI
- `Status` uses compact colored badges aligned with existing status language: `queued`, `sent`, `failed`, `completed`
- failed rows may show a short secondary failure reason within the status cell when available
- `Quick Action` renders `Retry` only when status is `failed`

### Retry Interaction
- Clicking `Retry` calls the existing retry client method with the row `request_id`
- Disable the row action while the retry is in flight
- On success, re-fetch the current page with the existing filters and offset
- On failure, show inline or page-level feedback without resetting filters or pagination

### Pagination
- Use simple previous/next controls
- Prev is disabled at offset `0`
- Next is disabled when the current page does not contain a full page of results or when `offset + items.length >= total`
- Default page size remains aligned with the backend default unless the page explicitly passes `limit`

## Data Flow
1. On page mount, fetch current user context if needed and fetch global actions with default filters.
2. Read available run dates using the same client pattern already used by the Command Center so `run_date` filtering is consistent with known pipeline runs.
3. Store `items`, `total`, `limit`, `offset`, loading state, active filters, and retry state in page-local state.
4. Re-fetch whenever filters or pagination change.

## Visual Direction
Follow the established dark glass Command Center visual language, but with denser, audit-oriented spacing:
- less emphasis on summary cards
- stronger focus on table readability
- keep the surface treatments, borders, and typography consistent with existing pages
- preserve mobile usability by allowing horizontal table scrolling rather than redesigning into cards for this pass

## Error And Empty States
- Loading: table-shaped skeleton rows
- Empty: centered empty state with a message indicating no actions match the current filters
- Error: inline banner above the table with the fetch error and a retry path via the refresh control

## Testing
Add frontend coverage for:
- loading state
- empty state
- successful table render
- filter-driven fetch behavior
- retry button visible only for failed rows
- retry success triggers a refresh of the current page

Also ensure API client coverage exists for `getGlobalActions`, including query-string construction for active filters.

## Files Expected To Change
- `frontend/src/app/actions/page.tsx`
- `frontend/src/app/page.tsx` or shared navigation location used by the Command Center
- `frontend/src/lib/api.test.ts`
- new page test file for the action history route

## Open Decisions Resolved
- Page style: audit-first
- Interaction pattern: single dense table, no expandable rows in v1
- Mobile handling: horizontal scroll table instead of card conversion
