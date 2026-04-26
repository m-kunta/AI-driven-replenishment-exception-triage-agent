import React, { useState } from "react";
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-md overflow-hidden">
        <div className="p-5 border-b border-slate-800 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-slate-100">Take Action</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 flex flex-col gap-4">
          {error && <div className="text-red-400 text-sm bg-red-400/10 p-2 rounded">{error}</div>}
          
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Action Type</label>
            <select
              value={actionType}
              onChange={(e) => setActionType(e.target.value as ActionType)}
              className="w-full bg-slate-800 border border-slate-700 rounded-md p-2 text-sm text-slate-200"
            >
              {allowedActionTypes.map((type) => (
                <option key={type} value={type}>
                  {ACTION_LABELS[type]}
                </option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Notes / Payload</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add details for this action..."
              className="w-full bg-slate-800 border border-slate-700 rounded-md p-2 text-sm text-slate-200 h-24"
            />
          </div>
          
          <div className="flex justify-end gap-3 mt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
            <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm bg-emerald-600/90 hover:bg-emerald-500 rounded-md text-white disabled:opacity-50 transition-colors">
              {isSubmitting ? "Sending..." : "Confirm Action"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
