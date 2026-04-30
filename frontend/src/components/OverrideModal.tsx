import React, { useMemo, useState } from "react";
import { createPortal } from "react-dom";

import {
  api,
  OverrideSubmitRequest,
  OverrideSubmitResponse,
  Priority,
  TriageResult,
} from "../lib/api";

type OverrideModalProps = {
  isOpen: boolean;
  exception: TriageResult;
  runDate: string;
  onClose: () => void;
  onSubmitted: (message: string) => void;
  submitOverride?: (payload: OverrideSubmitRequest) => Promise<OverrideSubmitResponse>;
};

const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function toRiskString(risks: string[] | undefined): string {
  return (risks ?? []).join(", ");
}

export default function OverrideModal({
  isOpen,
  exception,
  runDate,
  onClose,
  onSubmitted,
  submitOverride = api.submitOverride,
}: OverrideModalProps) {
  const snapshot = useMemo<Record<string, unknown>>(
    () => ({ ...exception }),
    [exception]
  );
  const [priority, setPriority] = useState<Priority>(exception.priority);
  const [rootCause, setRootCause] = useState(exception.root_cause ?? "");
  const [recommendedAction, setRecommendedAction] = useState(
    exception.recommended_action ?? ""
  );
  const [financialImpact, setFinancialImpact] = useState(
    exception.financial_impact_statement ?? ""
  );
  const [plannerBrief, setPlannerBrief] = useState(exception.planner_brief ?? "");
  const [compoundingRisks, setCompoundingRisks] = useState(
    toRiskString(exception.compounding_risks)
  );
  const [analystNote, setAnalystNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const payload: OverrideSubmitRequest = {
        exception_id: exception.exception_id,
        run_date: runDate,
        enriched_input_snapshot: snapshot,
        override_priority: priority,
        override_root_cause: rootCause.trim() || undefined,
        override_recommended_action: recommendedAction.trim() || undefined,
        override_financial_impact_statement: financialImpact.trim() || undefined,
        override_planner_brief: plannerBrief.trim() || undefined,
        override_compounding_risks: compoundingRisks
          .split(",")
          .map((risk) => risk.trim())
          .filter(Boolean),
        analyst_note: analystNote.trim() || undefined,
      };

      const response = await submitOverride(payload);
      onSubmitted(response.message ?? "Override submitted for review");
      onClose();
    } catch (submitError: unknown) {
      setError(
        submitError instanceof Error ? submitError.message : "Failed to submit override"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/85 p-4 sm:p-6">
      <div className="flex min-h-full items-center justify-center">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="override-modal-title"
          className="w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-700/70 bg-slate-900 shadow-2xl"
        >
          <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-6 py-5">
            <div>
              <h2 id="override-modal-title" className="text-xl font-semibold text-slate-100">
                Submit Override
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                Capture analyst corrections for {exception.item_name || exception.item_id}.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <form className="flex max-h-[90vh] flex-col" onSubmit={handleSubmit}>
            <div className="grid gap-4 overflow-y-auto px-6 py-5">
              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-priority">
                Priority
                <select
                  id="override-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                >
                  {PRIORITIES.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-root-cause">
                Root Cause
                <textarea
                  id="override-root-cause"
                  value={rootCause}
                  onChange={(e) => setRootCause(e.target.value)}
                  className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                />
              </label>

              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-recommended-action">
                Recommended Action
                <textarea
                  id="override-recommended-action"
                  value={recommendedAction}
                  onChange={(e) => setRecommendedAction(e.target.value)}
                  className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                />
              </label>

              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-financial-impact">
                Financial Impact
                <textarea
                  id="override-financial-impact"
                  value={financialImpact}
                  onChange={(e) => setFinancialImpact(e.target.value)}
                  className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                />
              </label>

              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-planner-brief">
                Planner Brief
                <textarea
                  id="override-planner-brief"
                  value={plannerBrief}
                  onChange={(e) => setPlannerBrief(e.target.value)}
                  className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                />
              </label>

              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-compounding-risks">
                Compounding Risks
                <input
                  id="override-compounding-risks"
                  value={compoundingRisks}
                  onChange={(e) => setCompoundingRisks(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                />
              </label>

              <label className="grid gap-1 text-sm text-slate-300" htmlFor="override-analyst-note">
                Analyst Note
                <textarea
                  id="override-analyst-note"
                  value={analystNote}
                  onChange={(e) => setAnalystNote(e.target.value)}
                  className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                />
              </label>

              {error && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                  {error}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-800 px-6 py-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-slate-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {submitting ? "Submitting..." : "Submit Override"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>,
    document.body
  );
}
