import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import ActionsPage from "./page";
import { api, ActionRecord } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getGlobalActions: jest.fn(),
      getRuns: jest.fn(),
    },
  };
});

const mockGetGlobalActions = api.getGlobalActions as jest.MockedFunction<typeof api.getGlobalActions>;
const mockGetRuns = api.getRuns as jest.MockedFunction<typeof api.getRuns>;

const makeRecord = (overrides: Partial<ActionRecord> = {}): ActionRecord => ({
  request_id: "req-1",
  exception_id: "EXC-1",
  run_date: "2026-07-01",
  action_type: "VENDOR_FOLLOW_UP",
  status: "completed",
  requested_by: "alice",
  requested_by_role: "planner",
  payload: {},
  created_at: "2026-07-01T09:00:00Z",
  updated_at: "2026-07-01T09:00:05Z",
  ...overrides,
});

beforeEach(() => {
  jest.clearAllMocks();
  mockGetRuns.mockResolvedValue(["2026-07-01", "2026-06-30"]);
});

test("renders action rows", async () => {
  mockGetGlobalActions.mockResolvedValue({ items: [makeRecord()], total: 1, limit: 50, offset: 0 });
  render(<ActionsPage />);
  await waitFor(() => expect(screen.getByText("EXC-1")).toBeInTheDocument());
  expect(screen.getAllByText("VENDOR_FOLLOW_UP").length).toBeGreaterThan(0);
});

test("shows empty state", async () => {
  mockGetGlobalActions.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
  render(<ActionsPage />);
  await waitFor(() => expect(screen.getByText(/no actions/i)).toBeInTheDocument());
});

test("shows backend unavailable error banner", async () => {
  mockGetGlobalActions.mockRejectedValue(new Error("Backend is not running. Start it with `bash scripts/dev.sh` after setting API_PASSWORD in .env."));
  render(<ActionsPage />);
  await waitFor(() =>
    expect(screen.getByText(/Backend is not running/i)).toBeInTheDocument()
  );
});

test("refetches when status filter changes", async () => {
  mockGetGlobalActions.mockResolvedValue({ items: [makeRecord()], total: 1, limit: 50, offset: 0 });
  render(<ActionsPage />);
  await waitFor(() => expect(mockGetGlobalActions).toHaveBeenCalledTimes(1));

  fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "failed" } });

  await waitFor(() => expect(mockGetGlobalActions).toHaveBeenCalledTimes(2));
  expect(mockGetGlobalActions).toHaveBeenLastCalledWith(
    expect.objectContaining({ status: "failed", offset: 0 })
  );
});

test("paginates with next/prev", async () => {
  mockGetGlobalActions.mockResolvedValue({
    items: [makeRecord()],
    total: 120,
    limit: 50,
    offset: 0,
  });
  render(<ActionsPage />);
  await waitFor(() => expect(mockGetGlobalActions).toHaveBeenCalledTimes(1));

  const nextButton = screen.getByRole("button", { name: /next/i });
  fireEvent.click(nextButton);

  await waitFor(() => expect(mockGetGlobalActions).toHaveBeenCalledTimes(2));
  expect(mockGetGlobalActions).toHaveBeenLastCalledWith(
    expect.objectContaining({ offset: 50 })
  );
});
