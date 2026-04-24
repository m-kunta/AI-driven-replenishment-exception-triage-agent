import React, { useState, useEffect } from "react";
import { TriageResult, Priority, ActionRecord, api } from "../lib/api";
import OverrideModal from "./OverrideModal";
import ActionModal from "./ActionModal";

interface ExceptionCardProps {
  exception: TriageResult;
  runDate?: string;
}

const PriorityColors: Record<Priority, string> = {
  CRITICAL: "text-red-400 bg-red-400/10 border-red-400/20",
  HIGH: "text-orange-400 bg-orange-400/10 border-orange-400/20",
  MEDIUM: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
  LOW: "text-slate-400 bg-slate-400/10 border-slate-400/20",
};

export default function ExceptionCard({ exception, runDate }: ExceptionCardProps) {
  const isPhantom = exception.phantom_flag;
  const priorityColor = PriorityColors[exception.priority];
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [actionModalOpen, setActionModalOpen] = useState(false);
  const [actions, setActions] = useState<ActionRecord[]>([]);
  const [submissionMessage, setSubmissionMessage] = useState<string | null>(null);
  const effectiveRunDate = runDate || exception.exception_date || new Date().toISOString().split("T")[0];

  useEffect(() => {
    // Load initial actions
    api.getActions(exception.exception_id)
       .then(setActions)
       .catch(console.error);
  }, [exception.exception_id]);

  const handleActionSubmitted = (record: ActionRecord) => {
    setActions(prev => [record, ...prev.filter(a => a.request_id !== record.request_id)]);
    setSubmissionMessage(`Action '${record.action_type}' queued successfully`);
    setTimeout(() => setSubmissionMessage(null), 5000);
  };

  const handleRetryAction = async (requestId: string) => {
    try {
      const record = await api.retryAction(requestId);
      setActions(prev => prev.map(a => a.request_id === requestId ? record : a));
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="glass glass-hover transition-all-smooth rounded-xl p-5 flex flex-col gap-4 relative overflow-hidden group">
      {/* Top Banner */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`text-xs font-bold px-2.5 py-1 rounded-md border uppercase tracking-wider ${priorityColor}`}
            >
              {exception.priority}
            </span>
            {isPhantom && (
              <span className="text-xs font-bold px-2.5 py-1 rounded-md border text-purple-400 bg-purple-400/10 border-purple-400/20 uppercase tracking-wider">
                PHANTOM DETECTED
              </span>
            )}
            <span className="text-xs text-slate-400 uppercase tracking-wider">
              {exception.exception_type}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-slate-100 mt-2">
            {exception.item_name || exception.item_id || "Unknown Item"}
          </h3>
          <p className="text-sm text-slate-400">
            Store: {exception.store_name || exception.store_id}
            {exception.store_tier && ` (Tier ${exception.store_tier})`}
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => setOverrideOpen(true)}
              className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-200 transition-colors hover:border-blue-400 hover:text-blue-300"
            >
              Override
            </button>
            <button
              type="button"
              onClick={() => setActionModalOpen(true)}
              className="rounded-md border border-emerald-600/50 bg-emerald-600/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-emerald-300 transition-colors hover:border-emerald-500 hover:text-emerald-200"
            >
              Take Action
            </button>
          </div>
        </div>
        
        {/* Financial Impact */}
        {!!exception.est_lost_sales_value && (
          <div className="text-right">
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Est. Lost Sales</p>
            <p className="text-xl font-bold text-red-400">
              ${exception.est_lost_sales_value.toLocaleString()}
            </p>
          </div>
        )}
      </div>

      {/* AI Reasoning Section */}
      <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
          AI Root Cause
        </h4>
        <p className="text-sm text-slate-200 mb-3">{exception.root_cause}</p>
        
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
          Recommended Action
        </h4>
        <p className="text-sm text-blue-200 font-medium">{exception.recommended_action}</p>
      </div>

      {/* Action History Section */}
      {actions.length > 0 && (
        <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/30">
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Action History</h4>
          <div className="flex flex-col gap-2">
            {actions.map(action => (
              <div key={action.request_id} className="flex justify-between items-center bg-slate-800/80 p-2 rounded text-xs">
                <div>
                  <span className="text-slate-300 font-medium">{action.action_type}</span>
                  <span className="text-slate-500 ml-2">by {action.requested_by}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded uppercase tracking-wider text-[10px] ${
                    action.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' :
                    action.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                    'bg-blue-500/20 text-blue-400'
                  }`}>
                    {action.status}
                  </span>
                  {action.status === 'failed' && (
                    <button onClick={() => handleRetryAction(action.request_id)} className="text-slate-400 hover:text-white underline transition-colors">Retry</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer Meta */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-auto pt-2 text-xs text-slate-500">
        {exception.promo_active && (
          <span className="flex items-center gap-1 text-emerald-400">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.381z" /></svg>
            Active Promo
          </span>
        )}
        {exception.dc_inventory_days !== undefined && (
          <span>DC Supply: {exception.dc_inventory_days}d</span>
        )}
        {exception.vendor_fill_rate_90d !== undefined && (
          <span>Vendor Fill: {(exception.vendor_fill_rate_90d * 100).toFixed(1)}%</span>
        )}
        <span className="ml-auto">ID: {exception.exception_id.split("-")[0]}</span>
      </div>

      {submissionMessage && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          {submissionMessage}
        </div>
      )}

      <OverrideModal
        isOpen={overrideOpen}
        exception={exception}
        runDate={effectiveRunDate}
        onClose={() => setOverrideOpen(false)}
        onSubmitted={(message) => setSubmissionMessage(message)}
      />

      <ActionModal
        isOpen={actionModalOpen}
        exceptionId={exception.exception_id}
        runDate={effectiveRunDate}
        onClose={() => setActionModalOpen(false)}
        onSubmitted={handleActionSubmitted}
      />
    </div>
  );
}
