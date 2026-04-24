import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import OverrideModal from "./OverrideModal";
import { TriageResult } from "../lib/api";

const baseException: TriageResult = {
  exception_id: "EXC-12345-abcd",
  priority: "CRITICAL",
  confidence: "HIGH",
  root_cause: "Vendor delivery delayed by 3 days.",
  recommended_action: "Expedite next shipment.",
  financial_impact_statement: "High risk of stockout.",
  planner_brief: "Brief description.",
  compounding_risks: ["promo_overlap"],
  missing_data_flags: [],
  phantom_flag: false,
  item_id: "ITM-001",
  item_name: "Premium Oat Milk",
  store_id: "STR-001",
  store_name: "NYC Flagship",
  exception_type: "OOS",
  exception_date: "2026-04-23",
  days_of_supply: 0,
  store_tier: 1,
  promo_active: true,
  est_lost_sales_value: 12500,
  promo_margin_at_risk: 700,
  dc_inventory_days: 14,
  vendor_fill_rate_90d: 0.887,
};

describe("OverrideModal", () => {
  it("renders all override fields when open", () => {
    render(
      <OverrideModal
        isOpen
        exception={baseException}
        runDate="2026-04-23"
        onClose={() => {}}
        onSubmitted={() => {}}
      />
    );

    expect(screen.getByRole("dialog", { name: /submit override/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/priority/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/root cause/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/recommended action/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/financial impact/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/planner brief/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/compounding risks/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/analyst note/i)).toBeInTheDocument();
  });

  it("submits a full override payload", async () => {
    const submitOverride = jest.fn().mockResolvedValue({ id: 1, status: "pending" });
    const onSubmitted = jest.fn();

    render(
      <OverrideModal
        isOpen
        exception={baseException}
        runDate="2026-04-23"
        onClose={() => {}}
        onSubmitted={onSubmitted}
        submitOverride={submitOverride}
      />
    );

    fireEvent.change(screen.getByLabelText(/root cause/i), {
      target: { value: "Count error" },
    });
    fireEvent.change(screen.getByLabelText(/recommended action/i), {
      target: { value: "Check store count" },
    });
    fireEvent.change(screen.getByLabelText(/financial impact/i), {
      target: { value: "Lower impact than forecast" },
    });
    fireEvent.change(screen.getByLabelText(/planner brief/i), {
      target: { value: "Investigate phantom inventory" },
    });
    fireEvent.change(
      screen.getByLabelText(/compounding risks/i),
      {
        target: {
          value: "POTENTIAL_PHANTOM_INVENTORY, vendor_late",
        },
      }
    );
    fireEvent.change(screen.getByLabelText(/analyst note/i), {
      target: { value: "Likely count issue" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit override/i }));

    await waitFor(() =>
      expect(submitOverride).toHaveBeenCalledWith(
        expect.objectContaining({
          exception_id: "EXC-12345-abcd",
          run_date: "2026-04-23",
          enriched_input_snapshot: expect.objectContaining({
            exception_id: "EXC-12345-abcd",
            item_id: "ITM-001",
          }),
          override_priority: "CRITICAL",
          override_root_cause: "Count error",
          override_recommended_action: "Check store count",
          override_financial_impact_statement: "Lower impact than forecast",
          override_planner_brief: "Investigate phantom inventory",
          override_compounding_risks: [
            "POTENTIAL_PHANTOM_INVENTORY",
            "vendor_late",
          ],
          analyst_note: "Likely count issue",
        })
      )
    );
    expect(onSubmitted).toHaveBeenCalled();
  });

  it("shows an inline error when submit fails", async () => {
    const submitOverride = jest.fn().mockRejectedValue(new Error("boom"));

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

    fireEvent.change(screen.getByLabelText(/analyst note/i), {
      target: { value: "Check promo timing" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit override/i }));

    expect(await screen.findByText(/boom/i)).toBeInTheDocument();
  });
});
