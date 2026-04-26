import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import ActionModal from "./ActionModal";

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
});
