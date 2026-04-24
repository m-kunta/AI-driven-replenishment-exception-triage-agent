# Phase 12b Planner Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate planner review screen/tab that lists pending overrides and supports approve/reject actions with clear in-flight and error states.

**Architecture:** Reuse the shared frontend override model introduced in Session 1, add planner-specific API methods to the existing client, then build a focused page component for pending review. Keep the screen independent from the analyst queue while linking to it from the current dashboard.

**Tech Stack:** Next.js App Router, React, TypeScript, Jest, Testing Library

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `frontend/src/lib/api.ts` | Pending/approve/reject API methods and response types |
| Create | `frontend/src/app/planner-review/page.tsx` | Planner review screen |
| Create | `frontend/src/app/planner-review/page.test.tsx` | Planner page tests |
| Modify | `frontend/src/app/page.tsx` | Add navigation link/tab to planner review |

## Task 1: Add Planner Review API Methods

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/app/planner-review/page.test.tsx`

- [ ] **Step 1: Write the failing planner page fetch test**

```tsx
it("loads pending overrides on mount", async () => {
  const getPendingOverrides = jest.fn().mockResolvedValue([pendingOverride]);
  render(<PlannerReviewPage getPendingOverrides={getPendingOverrides} />);
  expect(await screen.findByText(/EXC-001/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand src/app/planner-review/page.test.tsx
```

Expected: FAIL because the page and client methods do not exist yet.

- [ ] **Step 3: Add API shapes and methods**

Add to `frontend/src/lib/api.ts`:

```ts
export interface PendingOverride {
  id: number;
  exception_id: string;
  run_date: string;
  analyst_username: string;
  submitted_at: string;
  enriched_input_snapshot: Record<string, unknown>;
  override_priority?: string | null;
  override_root_cause?: string | null;
  override_recommended_action?: string | null;
  override_financial_impact_statement?: string | null;
  override_planner_brief?: string | null;
  override_compounding_risks?: string[] | null;
  analyst_note?: string | null;
}
```

And methods:

```ts
getPendingOverrides: async (): Promise<PendingOverride[]> => { ... }
approveOverride: async (id: number) => { ... }
rejectOverride: async (id: number, reason?: string) => { ... }
```

- [ ] **Step 4: Run test to verify it still fails for the missing page**

Run:

```bash
cd frontend && npm test -- --runInBand src/app/planner-review/page.test.tsx
```

Expected: FAIL because the page component is still missing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add planner review API client methods"
```

## Task 2: Build Planner Review Screen

**Files:**
- Create: `frontend/src/app/planner-review/page.tsx`
- Create: `frontend/src/app/planner-review/page.test.tsx`

- [ ] **Step 1: Write the failing interaction tests**

```tsx
it("approves and removes a pending override", async () => {
  const approveOverride = jest.fn().mockResolvedValue({ status: "approved" });
  render(<PlannerReviewPage ... />);
  await user.click(await screen.findByRole("button", { name: /approve/i }));
  await waitFor(() => expect(approveOverride).toHaveBeenCalledWith(11));
});

it("captures a rejection reason before rejecting", async () => {
  const rejectOverride = jest.fn().mockResolvedValue({ status: "rejected" });
  render(<PlannerReviewPage ... />);
  await user.type(await screen.findByLabelText(/rejection reason/i), "Needs more evidence");
  await user.click(screen.getByRole("button", { name: /reject/i }));
  await waitFor(() => expect(rejectOverride).toHaveBeenCalledWith(11, "Needs more evidence"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand src/app/planner-review/page.test.tsx
```

Expected: FAIL because the page does not exist yet.

- [ ] **Step 3: Implement the page**

Create `frontend/src/app/planner-review/page.tsx` with:

- initial fetch via `api.getPendingOverrides()`,
- loading, empty, and error states,
- per-row approve and reject controls,
- inline rejection reason input,
- optimistic removal only after API success,
- disabled controls while the row is in flight.

Use a shape like:

```tsx
type PlannerReviewPageProps = {
  getPendingOverrides?: typeof api.getPendingOverrides;
  approveOverride?: typeof api.approveOverride;
  rejectOverride?: typeof api.rejectOverride;
};
```

This keeps the page easy to test without mocking `fetch` globally.

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd frontend && npm test -- --runInBand src/app/planner-review/page.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/planner-review/page.tsx frontend/src/app/planner-review/page.test.tsx
git commit -m "feat: add planner review screen"
```

## Task 3: Link Planner Review From The Dashboard

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Write the failing navigation test**

Add to the new page test or an existing homepage test:

```tsx
it("shows a link to planner review", () => {
  render(<Home />);
  expect(screen.getByRole("link", { name: /planner review/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand src/app/planner-review/page.test.tsx
```

Expected: FAIL because the home page has no planner-review navigation yet.

- [ ] **Step 3: Add the link/tab**

In `frontend/src/app/page.tsx`, add a visible navigation element:

```tsx
<Link
  href="/planner-review"
  className="..."
>
  Planner Review
</Link>
```

Place it near the current dashboard header so the separation between analyst and planner flows is clear.

- [ ] **Step 4: Run the planner and existing frontend tests**

Run:

```bash
cd frontend && npm test -- --runInBand src/app/planner-review/page.test.tsx ExceptionCard.test.tsx MarkdownBriefing.test.tsx route.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat: add planner review navigation"
```

## Self-Review

- Spec coverage: covers separate planner screen/tab, pending list, approve/reject flow, rejection reason, and focused frontend tests.
- Placeholder scan: no unresolved placeholders remain.
- Type consistency: uses one shared `PendingOverride` shape from `frontend/src/lib/api.ts`.
