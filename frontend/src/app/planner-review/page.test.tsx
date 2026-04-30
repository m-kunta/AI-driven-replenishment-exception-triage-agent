import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import PlannerReviewPage from "./page";
import Home from "../page";
import { api } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getCurrentUser: jest.fn(),
      getPendingOverrides: jest.fn(),
      getRuns: jest.fn(),
      getQueue: jest.fn(),
      getBriefing: jest.fn(),
    },
  };
});

const pendingOverride = {
  id: 11,
  exception_id: "EXC-001",
  run_date: "2026-04-23",
  analyst_username: "analyst1",
  submitted_at: "2026-04-23T13:00:00Z",
  enriched_input_snapshot: {
    exception_id: "EXC-001",
    item_name: "Premium Oat Milk",
    store_name: "NYC Flagship",
  },
  override_priority: "HIGH",
  override_root_cause: "Planner correction",
  override_recommended_action: "Check count",
  override_financial_impact_statement: "Lower than forecast",
  override_planner_brief: "Watch afternoon demand",
  override_compounding_risks: ["vendor_late"],
  analyst_note: "Store count issue likely",
};

describe("PlannerReviewPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue({ username: "admin", role: "analyst" });
    (api.getPendingOverrides as jest.Mock).mockResolvedValue([]);
    (api.getRuns as jest.Mock).mockResolvedValue([]);
    (api.getQueue as jest.Mock).mockResolvedValue([]);
    (api.getBriefing as jest.Mock).mockResolvedValue(null);
  });

  it("loads pending overrides on mount", async () => {
    const getPendingOverrides = jest.fn().mockResolvedValue([pendingOverride]);

    render(<PlannerReviewPage getPendingOverrides={getPendingOverrides} />);

    expect(await screen.findByText(/EXC-001/i)).toBeInTheDocument();
  });

  it("shows an empty state when no overrides are pending", async () => {
    const getPendingOverrides = jest.fn().mockResolvedValue([]);

    render(<PlannerReviewPage getPendingOverrides={getPendingOverrides} />);

    expect(
      await screen.findByText(/no pending overrides to review/i)
    ).toBeInTheDocument();
  });

  it("approves and removes a pending override", async () => {
    const getPendingOverrides = jest.fn().mockResolvedValue([pendingOverride]);
    const approveOverride = jest.fn().mockResolvedValue({ status: "approved" });

    render(
      <PlannerReviewPage
        getPendingOverrides={getPendingOverrides}
        approveOverride={approveOverride}
      />
    );

    fireEvent.click(await screen.findByRole("button", { name: /approve/i }));

    await waitFor(() => expect(approveOverride).toHaveBeenCalledWith(11));
    await waitFor(() =>
      expect(screen.queryByText(/EXC-001/i)).not.toBeInTheDocument()
    );
  });

  it("captures a rejection reason before rejecting", async () => {
    const getPendingOverrides = jest.fn().mockResolvedValue([pendingOverride]);
    const rejectOverride = jest.fn().mockResolvedValue({ status: "rejected" });

    render(
      <PlannerReviewPage
        getPendingOverrides={getPendingOverrides}
        rejectOverride={rejectOverride}
      />
    );

    fireEvent.change(await screen.findByLabelText(/rejection reason/i), {
      target: { value: "Needs more evidence" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));

    await waitFor(() =>
      expect(rejectOverride).toHaveBeenCalledWith(11, "Needs more evidence")
    );
  });

  it("shows a row-level error when approval fails", async () => {
    const getPendingOverrides = jest.fn().mockResolvedValue([pendingOverride]);
    const approveOverride = jest.fn().mockRejectedValue(new Error("approve failed"));

    render(
      <PlannerReviewPage
        getPendingOverrides={getPendingOverrides}
        approveOverride={approveOverride}
      />
    );

    fireEvent.click(await screen.findByRole("button", { name: /approve/i }));

    expect(await screen.findByText(/approve failed/i)).toBeInTheDocument();
    expect(screen.getByText(/EXC-001/i)).toBeInTheDocument();
  });

  it("shows a link to planner review from the dashboard", async () => {
    render(<Home />);
    expect(await screen.findByRole("link", { name: /planner review/i })).toBeInTheDocument();
  });

  it("re-fetches queues when the window regains focus", async () => {
    (api.getRuns as jest.Mock).mockResolvedValue(["2026-04-29"]);
    (api.getQueue as jest.Mock).mockResolvedValue([]);

    render(<Home />);
    await screen.findByRole("link", { name: /planner review/i });

    const initialCalls = (api.getQueue as jest.Mock).mock.calls.length;
    fireEvent.focus(window);

    await waitFor(() =>
      expect((api.getQueue as jest.Mock).mock.calls.length).toBeGreaterThan(initialCalls)
    );
  });

  it("shows a backend recovery banner on the dashboard when the actor profile cannot load", async () => {
    (api.getCurrentUser as jest.Mock).mockRejectedValue(
      new Error("Backend is not running. Start it with `bash scripts/dev.sh` after setting API_PASSWORD in .env.")
    );

    render(<Home />);

    expect(await screen.findByText(/backend is not running/i)).toBeInTheDocument();
    expect(screen.getByText(/bash scripts\/dev\.sh/i)).toBeInTheDocument();
  });

  it("shows a back link to the Command Center", async () => {
    const getPendingOverrides = jest.fn().mockResolvedValue([]);
    render(<PlannerReviewPage getPendingOverrides={getPendingOverrides} />);

    const backLink = await screen.findByRole("link", { name: /command center/i });
    expect(backLink).toBeInTheDocument();
    expect(backLink).toHaveAttribute("href", "/");
  });

  it("shows a backend recovery banner on planner review when pending overrides cannot load", async () => {
    const getPendingOverrides = jest.fn().mockRejectedValue(
      new Error("Backend is not running. Start it with `bash scripts/dev.sh` after setting API_PASSWORD in .env.")
    );

    render(<PlannerReviewPage getPendingOverrides={getPendingOverrides} />);

    expect(await screen.findByText(/backend is not running/i)).toBeInTheDocument();
    expect(screen.getByText(/bash scripts\/dev\.sh/i)).toBeInTheDocument();
  });
});
