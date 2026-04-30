"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { api, TriageResult, Priority, PipelineTriggerRequest, ActorRole } from "../lib/api";
import ExceptionCard from "../components/ExceptionCard";
import MarkdownBriefing from "../components/MarkdownBriefing";

const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

type PipelineStatus =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export default function Home() {
  const [queues, setQueues] = useState<Record<Priority, TriageResult[]>>({
    CRITICAL: [],
    HIGH: [],
    MEDIUM: [],
    LOW: [],
  });
  const [activeTab, setActiveTab] = useState<Priority>("CRITICAL");
  const [loading, setLoading] = useState(false);
  // Start empty — wait for getRuns to select the most recent run before fetching queues.
  // This prevents an immediate 404 burst against today's date when no run exists yet.
  const [runDate, setRunDate] = useState("");
  const [availableRuns, setAvailableRuns] = useState<string[]>([]);
  const [briefing, setBriefing] = useState<string | null>(null);
  const [briefingExpanded, setBriefingExpanded] = useState(true);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({ kind: "idle" });
  const [adminExpanded, setAdminExpanded] = useState(false);
  const [actorRole, setActorRole] = useState<ActorRole | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  const fetchQueues = useCallback(async () => {
    if (!runDate) return; // wait until a run date is selected
    setLoading(true);
    setQueueError(null);
    try {
      const [results, briefingData] = await Promise.all([
        Promise.all(PRIORITIES.map((p) => api.getQueue(p, runDate).catch(() => []))),
        api.getBriefing(runDate).catch(() => null),
      ]);

      setQueues({
        CRITICAL: results[0],
        HIGH: results[1],
        MEDIUM: results[2],
        LOW: results[3],
      });
      setBriefing(briefingData?.content ?? null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setQueueError(`Failed to fetch queues: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [runDate]);

  const fetchUser = useCallback(async () => {
    try {
      const user = await api.getCurrentUser();
      setActorRole(user.role);
      setBackendError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setActorRole(null);
      setBackendError(message);
    }
  }, []);

  // Fetch available run dates on mount and pre-select the most recent
  useEffect(() => {
    api.getRuns().then((dates) => {
      if (dates.length > 0) {
        setAvailableRuns(dates);
        setRunDate(dates[0]); // already sorted newest-first by the backend
      } else {
        // No runs yet — fall back to today so the date picker is usable
        setRunDate(new Date().toISOString().split("T")[0]);
      }
    }).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : "Unknown error";
      setBackendError(message);
      // Fall back to today so the UI isn't stuck with an empty date
      setRunDate(new Date().toISOString().split("T")[0]);
    });
    fetchUser();
  }, [fetchUser]);

  useEffect(() => {
    fetchQueues();
  }, [fetchQueues]);

  useEffect(() => {
    const handleFocus = () => {
      fetchQueues();
      fetchUser();
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        fetchQueues();
        fetchUser();
      }
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchQueues, fetchUser]);

  const handleTrigger = async (triggerPayload: PipelineTriggerRequest) => {
    setPipelineStatus({ kind: "running" });
    try {
      await api.triggerPipeline(triggerPayload);
      setPipelineStatus({
        kind: "success",
        message: "Pipeline queued — refresh in ~30s to see results.",
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setPipelineStatus({ kind: "error", message: `Trigger failed: ${message}` });
    }
  };

  const activeQueue = queues[activeTab] || [];
  const totalLostSales = activeQueue.reduce(
    (sum, item) => sum + (item.est_lost_sales_value || 0),
    0
  );
  const totalCritical = queues.CRITICAL.length;
  const totalItems = PRIORITIES.reduce((sum, p) => sum + queues[p].length, 0);

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
            Exception Copilot
          </h1>
          <p className="text-slate-400 mt-1">AI-Driven Triage Command Center</p>
          <Link
            href="/planner-review"
            className="mt-3 inline-flex rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-300 transition-colors hover:border-blue-400 hover:text-blue-300"
          >
            Planner Review
          </Link>
        </div>
        <div className="flex items-center gap-4 glass px-4 py-2 rounded-lg">
          <span className="text-xs text-slate-500 uppercase tracking-wider">Run</span>
          {availableRuns.length > 0 ? (
            <select
              value={runDate}
              onChange={(e) => setRunDate(e.target.value)}
              className="bg-transparent text-slate-200 border-none outline-none cursor-pointer"
            >
              {availableRuns.map((d) => (
                <option key={d} value={d} className="bg-slate-800 text-slate-200">
                  {d}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="date"
              value={runDate}
              onChange={(e) => setRunDate(e.target.value)}
              className="bg-transparent text-slate-200 border-none outline-none cursor-pointer"
            />
          )}
          <div className="w-px h-6 bg-slate-700" />
          <button
            onClick={fetchQueues}
            disabled={loading}
            className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
            title="Refresh"
          >
            <svg
              className={`w-5 h-5 ${loading ? "animate-spin" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </header>

      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="glass rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-red-400">{totalCritical}</p>
          <p className="text-xs text-slate-400 uppercase tracking-wider mt-1">Critical</p>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-slate-200">{totalItems}</p>
          <p className="text-xs text-slate-400 uppercase tracking-wider mt-1">Total Exceptions</p>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <p className="text-3xl font-bold text-orange-400">
            {totalItems > 0 ? `$${queues.CRITICAL.concat(queues.HIGH).reduce((s, i) => s + (i.est_lost_sales_value || 0), 0).toLocaleString()}` : "—"}
          </p>
          <p className="text-xs text-slate-400 uppercase tracking-wider mt-1">Critical + High at Risk</p>
        </div>
      </div>

      {/* Morning Briefing */}
      <section className="mb-8">
        <button
          onClick={() => setBriefingExpanded((v) => !v)}
          className="flex items-center gap-3 w-full text-left mb-3 group"
        >
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Today&apos;s Briefing
          </h2>
          <svg
            className={`w-4 h-4 text-slate-500 ml-auto transition-transform ${briefingExpanded ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {briefingExpanded && (
          <div className="glass rounded-xl p-5">
            {briefing ? (
              <MarkdownBriefing content={briefing} />
            ) : (
              <p className="text-slate-500 text-sm italic">
                No briefing available for {runDate}. Run the pipeline to generate one.
              </p>
            )}
          </div>
        )}
      </section>

      {/* Queue Error */}
      {backendError && (
        <div className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <p className="font-medium text-amber-100">Backend unavailable</p>
          <p className="mt-1 whitespace-pre-wrap">{backendError}</p>
        </div>
      )}
      {queueError && (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {queueError}
        </div>
      )}

      {/* Priority Tabs */}
      <div className="flex gap-2 mb-6 border-b border-slate-800 pb-px">
        {PRIORITIES.map((p) => {
          const count = queues[p].length;
          const isActive = activeTab === p;
          return (
            <button
              key={p}
              onClick={() => setActiveTab(p)}
              className={`px-5 py-3 text-sm font-semibold border-b-2 transition-colors ${
                isActive
                  ? "text-blue-400 border-blue-500"
                  : "text-slate-400 border-transparent hover:text-slate-300 hover:border-slate-700"
              }`}
            >
              {p}
              <span
                className={`ml-2 px-2 py-0.5 rounded-full text-xs ${
                  isActive ? "bg-blue-500/20" : "bg-slate-800"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Queue Info Bar */}
      <div className="flex justify-between items-end mb-6">
        <div>
          <h2 className="text-xl font-semibold text-slate-200">{activeTab} Priority Queue</h2>
          <p className="text-sm text-slate-400 mt-1">
            {activeQueue.length} item{activeQueue.length !== 1 ? "s" : ""} needing review.
          </p>
        </div>
        {totalLostSales > 0 && (
          <div className="text-right glass px-4 py-2 rounded-lg border-red-500/20">
            <p className="text-xs text-slate-400 uppercase">Value at Risk</p>
            <p className="text-lg font-bold text-red-400">${totalLostSales.toLocaleString()}</p>
          </div>
        )}
      </div>

      {/* Cards */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="glass rounded-xl p-5 h-48 animate-pulse flex flex-col justify-between"
            >
              <div className="h-6 bg-slate-700/50 rounded w-1/3" />
              <div className="h-4 bg-slate-700/50 rounded w-2/3" />
              <div className="h-20 bg-slate-800 rounded-lg mt-4" />
            </div>
          ))}
        </div>
      ) : activeQueue.length === 0 ? (
        <div className="glass rounded-xl p-12 text-center flex flex-col items-center justify-center">
          <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mb-4">
            <svg
              className="w-8 h-8 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h3 className="text-xl font-medium text-slate-300">Queue is empty</h3>
          <p className="text-slate-500 mt-2 max-w-md">
            No {activeTab} priority exceptions found for {runDate}.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-4">
          {activeQueue.map((item) => (
            <ExceptionCard
              key={item.exception_id}
              exception={item}
              runDate={runDate}
              actorRole={actorRole}
            />
          ))}
        </div>
      )}

      {/* Pipeline Admin Panel */}
      <div className="mt-12 border-t border-slate-800 pt-6">
        <button
          onClick={() => setAdminExpanded((v) => !v)}
          className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-400 transition-colors"
        >
          <svg
            className={`w-3 h-3 transition-transform ${adminExpanded ? "rotate-90" : ""}`}
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M7.293 4.707a1 1 0 011.414 0l5 5a1 1 0 010 1.414l-5 5a1 1 0 01-1.414-1.414L11.586 10 7.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
          Pipeline Controls
        </button>

        {adminExpanded && (
          <div className="mt-4 glass rounded-xl p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex-1 text-sm text-slate-400">
              Manually trigger a pipeline run for{" "}
              <span className="text-slate-200 font-medium">{runDate}</span>.{" "}
              Results appear after ~30s — use the refresh button above.
            </div>
            <button
              onClick={() =>
                handleTrigger({ run_date: runDate, sample: true, no_alerts: true })
              }
              disabled={pipelineStatus.kind === "running"}
              className={`px-4 py-2 rounded-md font-medium text-sm whitespace-nowrap transition-all-smooth flex-shrink-0 ${
                pipelineStatus.kind === "running"
                  ? "bg-slate-600 text-slate-300 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20"
              }`}
            >
              {pipelineStatus.kind === "running" ? "Running…" : "Trigger Pipeline"}
            </button>
          </div>
        )}

        {/* Inline pipeline status — replaces alert() */}
        {pipelineStatus.kind === "success" && (
          <div className="mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm flex justify-between items-center">
            {pipelineStatus.message}
            <button
              onClick={() => setPipelineStatus({ kind: "idle" })}
              className="ml-4 text-emerald-600 hover:text-emerald-400"
            >
              ✕
            </button>
          </div>
        )}
        {pipelineStatus.kind === "error" && (
          <div className="mt-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex justify-between items-center">
            {pipelineStatus.message}
            <button
              onClick={() => setPipelineStatus({ kind: "idle" })}
              className="ml-4 text-red-600 hover:text-red-400"
            >
              ✕
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
