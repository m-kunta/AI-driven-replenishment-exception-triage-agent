import React, { useState } from "react";
import { createPortal } from "react-dom";
import {
  ActionType,
  ActorRole,
  api,
  ActionRequest,
  ActionRecord,
  getAllowedActionTypes,
} from "../lib/api";

interface ActionModalProps {
  isOpen: boolean;
  exceptionId: string;
  runDate: string;
  actorRole?: ActorRole;
  onClose: () => void;
  onSubmitted: (record: ActionRecord) => void;
}

const ACTION_LABELS: Record<ActionType, string> = {
  CREATE_REVIEW: "Create Review",
  REQUEST_VERIFICATION: "Request Verification",
  VENDOR_FOLLOW_UP: "Vendor Follow-up",
  STORE_CHECK: "Store Check",
  DEFER: "Defer",
};

export default function ActionModal({
  isOpen,
  exceptionId,
  runDate,
  actorRole = "analyst",
  onClose,
  onSubmitted,
}: ActionModalProps) {
  const allowedActionTypes = getAllowedActionTypes(actorRole);
  const [actionType, setActionType] = useState<ActionType>(allowedActionTypes[0] ?? "CREATE_REVIEW");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const payload: ActionRequest = {
        request_id: crypto.randomUUID(),
        exception_id: exceptionId,
        run_date: runDate,
        action_type: actionType,
        payload: { notes },
      };
      const record = await api.submitAction(payload);
      onSubmitted(record);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to submit action");
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/85 p-4 sm:p-6">
      <div className="flex min-h-full items-center justify-center">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="action-modal-title"
          className="w-full max-w-lg overflow-hidden rounded-2xl border border-slate-700/70 bg-slate-900 shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <h2 id="action-modal-title" className="text-lg font-semibold text-slate-100">
              Take Action
            </h2>
            <button onClick={onClose} className="text-slate-400 hover:text-white">
              &times;
            </button>
          </div>
          <form onSubmit={handleSubmit} className="flex max-h-[85vh] flex-col">
            <div className="flex flex-col gap-4 overflow-y-auto px-5 py-5">
              {error && <div className="rounded text-sm text-red-400 bg-red-400/10 p-2">{error}</div>}

              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Action Type
                </label>
                <select
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value as ActionType)}
                  className="w-full rounded-md border border-slate-700 bg-slate-800 p-2 text-sm text-slate-200"
                >
                  {allowedActionTypes.map((type) => (
                    <option key={type} value={type}>
                      {ACTION_LABELS[type]}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Notes / Payload
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add details for this action..."
                  className="h-32 w-full rounded-md border border-slate-700 bg-slate-800 p-2 text-sm text-slate-200"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-800 px-5 py-4">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
              <button type="submit" disabled={isSubmitting} className="rounded-md bg-emerald-600/90 px-4 py-2 text-sm text-white transition-colors hover:bg-emerald-500 disabled:opacity-50">
                {isSubmitting ? "Sending..." : "Confirm Action"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>,
    document.body
  );
}
