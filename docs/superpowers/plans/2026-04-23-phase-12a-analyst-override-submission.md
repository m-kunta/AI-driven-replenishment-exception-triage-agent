# Phase 12a Analyst Override Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an analyst-facing inline override modal to the Command Center so analysts can submit full-field override corrections from an exception card.

**Architecture:** Extend the existing frontend API client with a typed override submission call, add a focused modal component for override entry, and connect it to `ExceptionCard` without changing the backend contract. Keep the UX local to the current dashboard and cover the flow with component-level tests.

**Tech Stack:** Next.js App Router, React, TypeScript, Jest, Testing Library

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `frontend/src/lib/api.ts` | Shared types and `submitOverride()` client method |
| Create | `frontend/src/components/OverrideModal.tsx` | Analyst modal UI and form state |
| Create | `frontend/src/components/OverrideModal.test.tsx` | Modal behavior and submission tests |
| Modify | `frontend/src/components/ExceptionCard.tsx` | Add inline `Override` entry point |
| Modify | `frontend/src/components/ExceptionCard.test.tsx` | Verify button/modal wiring |

## Task 1: Extend Frontend API Client For Override Submission

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/components/OverrideModal.test.tsx`

- [ ] **Step 1: Write the failing modal submit test**

```tsx
it("submits a full override payload", async () => {
  const submitOverride = jest.fn().mockResolvedValue({ id: 1, status: "pending" });
  render(
    <OverrideModal
      isOpen
      exception={baseException}
      runDate="2026-04-23"
      onClose={() => {}}
      onSubmitted={() => {}}
      submitOverride={submitOverride}
    />
  );

  await user.type(screen.getByLabelText(/root cause/i), "Count error");
  await user.click(screen.getByRole("button", { name: /submit override/i }));

  await waitFor(() =>
    expect(submitOverride).toHaveBeenCalledWith(
      expect.objectContaining({
        exception_id: "EXC-12345-abcd",
        run_date: "2026-04-23",
        enriched_input_snapshot: expect.any(Object),
      })
    )
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand src/components/OverrideModal.test.tsx
```

Expected: FAIL because `OverrideModal` and/or `submitOverride` plumbing does not exist yet.

- [ ] **Step 3: Add shared types and API method**

Add to `frontend/src/lib/api.ts`:

```ts
export interface OverrideSubmitRequest {
  exception_id: string;
  run_date: string;
  enriched_input_snapshot: Record<string, unknown>;
  override_priority?: Priority;
  override_root_cause?: string;
  override_recommended_action?: string;
  override_financial_impact_statement?: string;
  override_planner_brief?: string;
  override_compounding_risks?: string[];
  analyst_note?: string;
}

export interface OverrideSubmitResponse {
  id: number;
  status: "pending";
  message: string;
}
```

And add:

```ts
submitOverride: async (
  payload: OverrideSubmitRequest
): Promise<OverrideSubmitResponse> => {
  const res = await fetch(`${PROXY_BASE}/overrides`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Failed to submit override: ${res.statusText}`);
  }
  return res.json();
},
```

- [ ] **Step 4: Run test to confirm it still fails for the right reason**

Run:

```bash
cd frontend && npm test -- --runInBand src/components/OverrideModal.test.tsx
```

Expected: FAIL because the modal component itself is still missing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add frontend override submission client"
```

## Task 2: Build Override Modal Component

**Files:**
- Create: `frontend/src/components/OverrideModal.tsx`
- Create: `frontend/src/components/OverrideModal.test.tsx`

- [ ] **Step 1: Write the failing render and validation tests**

```tsx
it("renders all override fields when open", () => {
  render(
    <OverrideModal
      isOpen
      exception={baseException}
      runDate="2026-04-23"
      onClose={() => {}}
      onSubmitted={() => {}}
      submitOverride={jest.fn()}
    />
  );

  expect(screen.getByLabelText(/priority/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/root cause/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/recommended action/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/financial impact/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/planner brief/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/compounding risks/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/analyst note/i)).toBeInTheDocument();
});

it("shows an inline error when submit fails", async () => {
  const submitOverride = jest.fn().mockRejectedValue(new Error("boom"));
  render(/* same setup */);
  await user.type(screen.getByLabelText(/analyst note/i), "Check promo timing");
  await user.click(screen.getByRole("button", { name: /submit override/i }));
  expect(await screen.findByText(/boom/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand src/components/OverrideModal.test.tsx
```

Expected: FAIL because `OverrideModal.tsx` does not exist.

- [ ] **Step 3: Implement the minimal modal**

Create `frontend/src/components/OverrideModal.tsx` with:

```tsx
type Props = {
  isOpen: boolean;
  exception: TriageResult;
  runDate: string;
  onClose: () => void;
  onSubmitted: (message: string) => void;
  submitOverride?: (payload: OverrideSubmitRequest) => Promise<OverrideSubmitResponse>;
};
```

Include:

- controlled fields for all overrideable values,
- a compounding-risk text input parsed as comma-separated values,
- a submit button disabled while in flight,
- inline error state,
- snapshot builder using the current exception object,
- `null` render when `isOpen` is false.

Use the production default:

```ts
submitOverride = api.submitOverride
```

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
cd frontend && npm test -- --runInBand src/components/OverrideModal.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/OverrideModal.tsx frontend/src/components/OverrideModal.test.tsx
git commit -m "feat: add analyst override modal"
```

## Task 3: Wire Override Modal Into Exception Cards

**Files:**
- Modify: `frontend/src/components/ExceptionCard.tsx`
- Modify: `frontend/src/components/ExceptionCard.test.tsx`

- [ ] **Step 1: Write the failing ExceptionCard interaction test**

```tsx
it("opens the override modal from the card action", async () => {
  render(<ExceptionCard exception={base} runDate="2026-04-23" />);
  await user.click(screen.getByRole("button", { name: /override/i }));
  expect(screen.getByRole("dialog", { name: /submit override/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand src/components/ExceptionCard.test.tsx src/components/OverrideModal.test.tsx
```

Expected: FAIL because the card has no override entry point yet.

- [ ] **Step 3: Add the button and local modal state**

In `frontend/src/components/ExceptionCard.tsx`:

```tsx
const [overrideOpen, setOverrideOpen] = useState(false);
```

Render:

```tsx
<button
  onClick={() => setOverrideOpen(true)}
  className="..."
>
  Override
</button>

<OverrideModal
  isOpen={overrideOpen}
  exception={exception}
  runDate={runDate}
  onClose={() => setOverrideOpen(false)}
  onSubmitted={setBannerMessage}
/>
```

Add the `runDate` prop to the card contract and thread it from `frontend/src/app/page.tsx`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd frontend && npm test -- --runInBand src/components/ExceptionCard.test.tsx src/components/OverrideModal.test.tsx
```

Expected: PASS

- [ ] **Step 5: Run the broader frontend test set**

Run:

```bash
cd frontend && npm test -- --runInBand ExceptionCard.test.tsx MarkdownBriefing.test.tsx route.test.ts
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ExceptionCard.tsx frontend/src/components/ExceptionCard.test.tsx frontend/src/app/page.tsx
git commit -m "feat: wire analyst override modal into exception cards"
```

## Self-Review

- Spec coverage: covers analyst modal, inline entry point, full field capture, proxy-backed submission, and focused frontend tests.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: uses the existing `Priority` and `TriageResult` models from `frontend/src/lib/api.ts`.
