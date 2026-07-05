"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  ActionRecord,
  ActionStatus,
  AnyActionType,
  BACKEND_UNAVAILABLE_MESSAGE,
} from "../../lib/api";

const PAGE_SIZE = 50;

const STATUS_OPTIONS: ActionStatus[] = ["queued", "sent", "failed", "completed"];
const ACTION_TYPE_OPTIONS: AnyActionType[] = [
  "CREATE_REVIEW",
  "REQUEST_VERIFICATION",
  "VENDOR_FOLLOW_UP",
  "STORE_CHECK",
  "DEFER",
  "SETTINGS_CHANGE",
];

function Badge({ text, variant = "default" }: { text: string; variant?: "default" | "ok" | "warn" | "error" }) {
  const colours: Record<string, string> = {
    default: "bg-slate-700/60 text-slate-300",
    ok: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25",
    warn: "bg-amber-500/15 text-amber-300 border border-amber-500/25",
    error: "bg-rose-500/15 text-rose-300 border border-rose-500/25",
  };
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${colours[variant]}`}>
      {text}
    </span>
  );
}

function statusVariant(status: ActionStatus): "default" | "ok" | "warn" | "error" {
  switch (status) {
    case "completed":
      return "ok";
    case "failed":
      return "error";
    case "sent":
    case "queued":
      return "warn";
    default:
      return "default";
  }
}

function formatTimestamp(raw: string): string {
  try {
    return new Date(raw).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return raw;
  }
}

export default function ActionsPage() {
  const [items, setItems] = useState<ActionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("");
  const [actionTypeFilter, setActionTypeFilter] = useState<string>("");
  const [runDateFilter, setRunDateFilter] = useState<string>("");
  const [availableRuns, setAvailableRuns] = useState<string[]>([]);

  useEffect(() => {
    api.getRuns().then(setAvailableRuns).catch(() => setAvailableRuns([]));
  }, []);

  const fetchActions = useCallback(() => {
    let active = true;
    setLoading(true);
    setError(null);

    api
      .getGlobalActions({
        limit: PAGE_SIZE,
        offset,
        status: statusFilter || undefined,
        action_type: actionTypeFilter || undefined,
        run_date: runDateFilter || undefined,
      })
      .then((result) => {
        if (!active) return;
        setItems(result.items);
        setTotal(result.total);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load actions");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [offset, statusFilter, actionTypeFilter, runDateFilter]);

  useEffect(() => {
    const cleanup = fetchActions();
    return cleanup;
  }, [fetchActions]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setOffset(0);
  };

  const handleActionTypeChange = (value: string) => {
    setActionTypeFilter(value);
    setOffset(0);
  };

  const handleRunDateChange = (value: string) => {
    setRunDateFilter(value);
    setOffset(0);
  };

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

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
        <p className="text-xs uppercase tracking-wider text-slate-500">Action History</p>
        <h1 className="mt-2 text-3xl font-bold text-slate-100">Downstream Actions</h1>
        <p className="mt-2 text-sm text-slate-400">
          All actions submitted across every run, with filtering and pagination.
        </p>
      </header>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-end gap-4 glass rounded-xl p-4">
        <label className="flex flex-col gap-1 text-xs text-slate-400" htmlFor="status-filter">
          Status
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="rounded bg-slate-800 border border-slate-600 text-slate-200 text-sm px-2 py-1.5"
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-400" htmlFor="action-type-filter">
          Action Type
          <select
            id="action-type-filter"
            value={actionTypeFilter}
            onChange={(e) => handleActionTypeChange(e.target.value)}
            className="rounded bg-slate-800 border border-slate-600 text-slate-200 text-sm px-2 py-1.5"
          >
            <option value="">All</option>
            {ACTION_TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate-400" htmlFor="run-date-filter">
          Run Date
          <select
            id="run-date-filter"
            value={runDateFilter}
            onChange={(e) => handleRunDateChange(e.target.value)}
            className="rounded bg-slate-800 border border-slate-600 text-slate-200 text-sm px-2 py-1.5"
          >
            <option value="">All</option>
            {availableRuns.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <p className="font-medium text-red-200">
            {error === BACKEND_UNAVAILABLE_MESSAGE ? "Backend unavailable" : "Failed to load actions"}
          </p>
          <p className="mt-1 whitespace-pre-wrap">{error}</p>
        </div>
      )}

      {loading && (
        <div className="grid gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 rounded-xl bg-slate-900/60 animate-pulse" />
          ))}
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 px-6 py-12 text-center flex flex-col items-center justify-center">
          <p className="text-slate-300 font-medium">No actions recorded yet.</p>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className="overflow-x-auto glass rounded-xl">
            <table className="min-w-full text-sm text-left">
              <thead>
                <tr className="border-b border-slate-800 text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Exception</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Requested By</th>
                  <th className="px-4 py-3">Failure Reason</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.request_id} className="border-b border-slate-800/60 last:border-0">
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{formatTimestamp(item.created_at)}</td>
                    <td className="px-4 py-3 text-slate-200 font-mono">{item.exception_id}</td>
                    <td className="px-4 py-3 text-slate-300">{item.action_type}</td>
                    <td className="px-4 py-3">
                      <Badge text={item.status} variant={statusVariant(item.status)} />
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {item.requested_by} <span className="text-slate-600">({item.requested_by_role})</span>
                    </td>
                    <td className="px-4 py-3 text-rose-300">
                      {item.status === "failed" ? (item.failure_reason ?? "—") : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
            <p>
              Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                disabled={!hasPrev}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Prev
              </button>
              <button
                type="button"
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                disabled={!hasNext}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
