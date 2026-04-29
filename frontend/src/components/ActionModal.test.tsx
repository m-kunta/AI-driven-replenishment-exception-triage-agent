import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import ActionModal from "./ActionModal";
import { api } from "../lib/api";

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      submitAction: jest.fn(),
    },
  };
});

const mockSubmitAction = api.submitAction as jest.MockedFunction<typeof api.submitAction>;

describe("ActionModal", () => {
  const baseProps = {
    isOpen: true,
    exceptionId: "EXC-123",
    runDate: "2026-04-25",
    onClose: jest.fn(),
    onSubmitted: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------------------------------------------------------------------------
  // Role-based action filtering
  // ---------------------------------------------------------------------------

  it("shows only analyst-safe actions by default", () => {
    render(<ActionModal {...baseProps} />);

    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Create Review", "Request Verification", "Defer"]);
    expect(screen.queryByRole("option", { name: /store check/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /vendor follow-up/i })).not.toBeInTheDocument();
  });

  it("shows planner-only actions when actorRole is planner", () => {
    render(<ActionModal {...baseProps} actorRole="planner" />);

    expect(screen.getByRole("option", { name: /store check/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /vendor follow-up/i })).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Modal render
  // ---------------------------------------------------------------------------

  it("renders the modal title and confirm button when open", () => {
    render(<ActionModal {...baseProps} />);

    expect(screen.getByText("Take Action")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm action/i })).toBeInTheDocument();
  });

  it("renders nothing when isOpen is false", () => {
    render(<ActionModal {...baseProps} isOpen={false} />);

    expect(screen.queryByText("Take Action")).not.toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", () => {
    render(<ActionModal {...baseProps} />);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(baseProps.onClose).toHaveBeenCalledTimes(1);
  });

  // ---------------------------------------------------------------------------
  // Submission — loading state
  // ---------------------------------------------------------------------------

  it("shows Sending… while submitAction is pending", async () => {
    let resolve: (v: any) => void;
    mockSubmitAction.mockReturnValue(new Promise((r) => { resolve = r; }));

    render(<ActionModal {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm action/i }));

    expect(await screen.findByRole("button", { name: /sending/i })).toBeDisabled();
  });

  // ---------------------------------------------------------------------------
  // Submission — success
  // ---------------------------------------------------------------------------

  it("calls onSubmitted with the returned record and onClose on success", async () => {
    const record = {
      request_id: "req-1",
      exception_id: "EXC-123",
      run_date: "2026-04-25",
      action_type: "CREATE_REVIEW" as const,
      requested_by: "admin",
      requested_by_role: "analyst",
      payload: {},
      status: "completed" as const,
      created_at: "2026-04-25T00:00:00Z",
      updated_at: "2026-04-25T00:00:00Z",
    };
    mockSubmitAction.mockResolvedValue(record);

    render(<ActionModal {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm action/i }));

    await waitFor(() => {
      expect(baseProps.onSubmitted).toHaveBeenCalledWith(record);
      expect(baseProps.onClose).toHaveBeenCalled();
    });
  });

  it("passes the correct exception_id and run_date to submitAction", async () => {
    mockSubmitAction.mockResolvedValue({} as any);

    render(<ActionModal {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm action/i }));

    await waitFor(() => expect(mockSubmitAction).toHaveBeenCalled());
    const call = mockSubmitAction.mock.calls[0][0];
    expect(call.exception_id).toBe("EXC-123");
    expect(call.run_date).toBe("2026-04-25");
  });

  // ---------------------------------------------------------------------------
  // Submission — error state
  // ---------------------------------------------------------------------------

  it("shows an error message when submitAction rejects", async () => {
    mockSubmitAction.mockRejectedValue(new Error("Network failure"));

    render(<ActionModal {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm action/i }));

    expect(await screen.findByText("Network failure")).toBeInTheDocument();
  });

  it("re-enables the confirm button after a failed submission", async () => {
    mockSubmitAction.mockRejectedValue(new Error("oops"));

    render(<ActionModal {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: /confirm action/i }));

    await screen.findByText("oops");
    expect(screen.getByRole("button", { name: /confirm action/i })).not.toBeDisabled();
  });
});
