"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  api,
  PendingOverride,
} from "../../lib/api";

type PlannerReviewPageProps = {
  getPendingOverrides?: typeof api.getPendingOverrides;
  approveOverride?: typeof api.approveOverride;
  rejectOverride?: typeof api.rejectOverride;
};

type RowState = Record<number, { busy: boolean; error?: string; rejectionReason: string }>;

function defaultRowState() {
  return { busy: false, rejectionReason: "" };
}

export default function PlannerReviewPage({
  getPendingOverrides = api.getPendingOverrides,
  approveOverride = api.approveOverride,
  rejectOverride = api.rejectOverride,
}: PlannerReviewPageProps) {
  const [items, setItems] = useState<PendingOverride[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowState, setRowState] = useState<RowState>({});

  useEffect(() => {
    let active = true;

    getPendingOverrides()
      .then((pending) => {
        if (!active) return;
        setItems(pending);
      })
      .catch((loadError: unknown) => {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "Failed to load pending overrides");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [getPendingOverrides]);

  const setBusy = (id: number, busy: boolean) => {
    setRowState((current) => ({
      ...current,
      [id]: {
        ...(current[id] ?? defaultRowState()),
        busy,
      },
    }));
  };

  const setRowError = (id: number, message?: string) => {
    setRowState((current) => ({
      ...current,
      [id]: {
        ...(current[id] ?? defaultRowState()),
        busy: false,
        error: message,
      },
    }));
  };

  const handleApprove = async (id: number) => {
    setBusy(id, true);
    try {
      await approveOverride(id);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (approveError: unknown) {
      setRowError(
        id,
        approveError instanceof Error ? approveError.message : "Failed to approve override"
      );
    }
  };

  const handleReject = async (id: number) => {
    setBusy(id, true);
    try {
      const reason = rowState[id]?.rejectionReason || undefined;
      await rejectOverride(id, reason);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (rejectError: unknown) {
      setRowError(
        id,
        rejectError instanceof Error ? rejectError.message : "Failed to reject override"
      );
    }
  };

  const handleReasonChange = (id: number, value: string) => {
    setRowState((current) => ({
      ...current,
      [id]: {
        ...(current[id] ?? defaultRowState()),
        rejectionReason: value,
      },
    }));
  };

  return (
    <main className="min-h-screen max-w-7xl mx-auto p-8">
      <header className="mb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors mb-4"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
          </svg>
          Command Center
        </Link>
        <p className="text-xs uppercase tracking-wider text-slate-500">Planner Review</p>
        <h1 className="mt-2 text-3xl font-bold text-slate-100">Pending Override Decisions</h1>
        <p className="mt-2 text-sm text-slate-400">
          Review analyst-submitted corrections and promote only the overrides that should
          feed future triage runs.
        </p>
      </header>

      {loading && (
        <div className="grid gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 animate-pulse">
              <div className="flex justify-between mb-4">
                <div className="space-y-2">
                  <div className="h-5 w-32 rounded bg-slate-700/60" />
                  <div className="h-4 w-48 rounded bg-slate-800/80" />
                </div>
                <div className="h-6 w-24 rounded-full bg-slate-800/80" />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="h-24 rounded-xl bg-slate-800/60" />
                <div className="h-24 rounded-xl bg-slate-800/60" />
              </div>
            </div>
          ))}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <p className="font-medium text-red-200">Planner review is unavailable</p>
          <p className="mt-1 whitespace-pre-wrap">{error}</p>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 px-6 py-12 text-center flex flex-col items-center justify-center">
          <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mb-3">
            <svg className="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-slate-300 font-medium">No pending overrides to review.</p>
          <p className="text-slate-500 text-sm mt-1">All submissions have been processed.</p>
        </div>
      )}

      <div className="grid gap-4">
        {items.map((item) => {
          const state = rowState[item.id] ?? defaultRowState();
          const snapshot = item.enriched_input_snapshot;

          return (
            <section
              key={item.id}
              className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-lg"
            >
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-100">{item.exception_id}</h2>
                  <p className="text-sm text-slate-400">
                    Submitted by {item.analyst_username} on {item.submitted_at}
                  </p>
                </div>
                <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-blue-300">
                  Run {item.run_date}
                </span>
              </div>

              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-300">
                    Original Context
                  </h3>
                  <p className="text-sm text-slate-200">
                    {String(snapshot.item_name ?? snapshot.item_id ?? "Unknown Item")}
                  </p>
                  <p className="mt-1 text-sm text-slate-400">
                    {String(snapshot.store_name ?? snapshot.store_id ?? "Unknown Store")}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-300">
                    Proposed Override
                  </h3>
                  <div className="grid gap-2 text-sm text-slate-200">
                    {item.override_priority && <p>Priority: {item.override_priority}</p>}
                    {item.override_root_cause && <p>Root Cause: {item.override_root_cause}</p>}
                    {item.override_recommended_action && (
                      <p>Recommended Action: {item.override_recommended_action}</p>
                    )}
                    {item.override_financial_impact_statement && (
                      <p>Financial Impact: {item.override_financial_impact_statement}</p>
                    )}
                    {item.override_planner_brief && (
                      <p>Planner Brief: {item.override_planner_brief}</p>
                    )}
                    {!!item.override_compounding_risks?.length && (
                      <p>Compounding Risks: {item.override_compounding_risks.join(", ")}</p>
                    )}
                    {item.analyst_note && <p>Analyst Note: {item.analyst_note}</p>}
                  </div>
                </div>
              </div>

              <div className="mt-4 grid gap-3">
                <label className="grid gap-1 text-sm text-slate-300" htmlFor={`reject-${item.id}`}>
                  Rejection Reason
                  <input
                    id={`reject-${item.id}`}
                    value={state.rejectionReason}
                    onChange={(e) => handleReasonChange(item.id, e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200"
                  />
                </label>

                {state.error && (
                  <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                    {state.error}
                  </p>
                )}

                <div className="flex gap-3">
                  <button
                    type="button"
                    disabled={state.busy}
                    onClick={() => handleApprove(item.id)}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-700"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={state.busy}
                    onClick={() => handleReject(item.id)}
                    className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-rose-500 disabled:cursor-not-allowed disabled:bg-slate-700"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}
