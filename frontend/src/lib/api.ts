export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface TriageResult {
  exception_id: string;
  priority: Priority;
  confidence: string;
  root_cause: string;
  recommended_action: string;
  financial_impact_statement: string;
  planner_brief: string;
  compounding_risks: string[];
  missing_data_flags: string[];
  pattern_id?: string;
  escalated_from?: string;
  phantom_flag: boolean;
  reasoning_trace?: string;

  // Carried forward enrichment data
  item_id?: string;
  item_name?: string;
  store_id?: string;
  store_name?: string;
  exception_type?: string;
  exception_date?: string;
  days_of_supply?: number;
  store_tier?: number;
  promo_active?: boolean;
  est_lost_sales_value?: number;
  promo_margin_at_risk?: number;
  dc_inventory_days?: number;
  vendor_fill_rate_90d?: number;
}

export interface PipelineTriggerRequest {
  run_date?: string;
  sample?: boolean;
  no_alerts?: boolean;
  dry_run?: boolean;
}

export interface OverrideSubmitRequest {
  exception_id: string;
  run_date: string;
  enriched_input_snapshot: Record<string, unknown>;
  override_priority?: Priority;
  override_root_cause?: string;
  override_recommended_action?: string;
  override_financial_impact_statement?: string;
  override_planner_brief?: string;
  override_compounding_risks?: string[];
  analyst_note?: string;
}

export interface OverrideSubmitResponse {
  id: number;
  status: "pending";
  message?: string;
}

export interface PendingOverride {
  id: number;
  exception_id: string;
  run_date: string;
  analyst_username: string;
  submitted_at: string;
  enriched_input_snapshot: Record<string, unknown>;
  override_priority?: string | null;
  override_root_cause?: string | null;
  override_recommended_action?: string | null;
  override_financial_impact_statement?: string | null;
  override_planner_brief?: string | null;
  override_compounding_risks?: string[] | null;
  analyst_note?: string | null;
}

export interface OverrideDecisionResponse {
  status: "approved" | "rejected";
  override_id: number;
}

export type ActionType = "CREATE_REVIEW" | "REQUEST_VERIFICATION" | "VENDOR_FOLLOW_UP" | "STORE_CHECK" | "DEFER";
export type ActorRole = "analyst" | "planner";

export interface CurrentUser {
  username: string;
  role: ActorRole;
}

export const ANALYST_ACTION_TYPES: ActionType[] = [
  "CREATE_REVIEW",
  "REQUEST_VERIFICATION",
  "DEFER",
];

export const PLANNER_ACTION_TYPES: ActionType[] = [
  "CREATE_REVIEW",
  "REQUEST_VERIFICATION",
  "VENDOR_FOLLOW_UP",
  "STORE_CHECK",
  "DEFER",
];

export function getAllowedActionTypes(role: ActorRole): ActionType[] {
  return role === "planner" ? PLANNER_ACTION_TYPES : ANALYST_ACTION_TYPES;
}

export type ActionStatus = "queued" | "sent" | "failed" | "completed";

export interface ActionRequest {
  request_id: string;
  exception_id: string;
  run_date: string;
  action_type: ActionType;
  payload: Record<string, unknown>;
}

export interface ActionRecord {
  request_id: string;
  exception_id: string;
  run_date: string;
  action_type: ActionType;
  requested_by: string;
  requested_by_role: string;
  payload: Record<string, unknown>;
  status: ActionStatus;
  created_at: string;
  updated_at: string;
  failure_reason?: string | null;
  downstream_response?: Record<string, unknown> | null;
}

// All requests route through the Next.js server-side proxy at /api/proxy,
// which injects Basic Auth credentials from server-only env vars. No credential
// is ever sent to the browser.
const PROXY_BASE = "/api/proxy";

const JSON_HEADERS = { "Content-Type": "application/json" };

export const BACKEND_UNAVAILABLE_MESSAGE =
  "Backend is not running. Start it with `bash scripts/dev.sh` after setting API_PASSWORD in .env.";

async function toApiError(
  res: Response,
  fallback: string
): Promise<Error> {
  const body = await res.json().catch(() => ({}));
  const detail =
    typeof body?.detail === "string" && body.detail.length > 0
      ? body.detail
      : null;

  if (res.status === 502 || detail?.includes("Backend unreachable")) {
    return new Error(BACKEND_UNAVAILABLE_MESSAGE);
  }

  return new Error(detail ?? fallback);
}

export const api = {
  triggerPipeline: async (payload: PipelineTriggerRequest) => {
    const res = await fetch(`${PROXY_BASE}/pipeline/trigger`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to trigger pipeline: ${res.statusText}`);
    }
    return res.json();
  },

  submitOverride: async (
    payload: OverrideSubmitRequest
  ): Promise<OverrideSubmitResponse> => {
    const res = await fetch(`${PROXY_BASE}/overrides`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to submit override: ${res.statusText}`);
    }
    return res.json();
  },

  getPendingOverrides: async (): Promise<PendingOverride[]> => {
    const res = await fetch(`${PROXY_BASE}/overrides/pending`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to fetch pending overrides: ${res.statusText}`);
    }
    return res.json();
  },

  approveOverride: async (id: number): Promise<OverrideDecisionResponse> => {
    const res = await fetch(`${PROXY_BASE}/overrides/${id}/approve`, {
      method: "POST",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to approve override: ${res.statusText}`);
    }
    return res.json();
  },

  rejectOverride: async (
    id: number,
    reason?: string
  ): Promise<OverrideDecisionResponse> => {
    const res = await fetch(`${PROXY_BASE}/overrides/${id}/reject`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to reject override: ${res.statusText}`);
    }
    return res.json();
  },

  getQueue: async (priority: Priority, runDate: string): Promise<TriageResult[]> => {
    const res = await fetch(`${PROXY_BASE}/exceptions/queue/${priority}/${runDate}`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      if (res.status === 404) return [];
      throw await toApiError(res, `Failed to fetch queue: ${res.statusText}`);
    }
    return res.json();
  },

  getRuns: async (): Promise<string[]> => {
    const res = await fetch(`${PROXY_BASE}/runs`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      if (res.status === 502) {
        throw await toApiError(res, `Failed to fetch runs: ${res.statusText}`);
      }
      return [];
    }
    const data = await res.json();
    return data.run_dates ?? [];
  },

  getBriefing: async (runDate: string): Promise<{ run_date: string; content: string } | null> => {
    const res = await fetch(`${PROXY_BASE}/briefing/${runDate}`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      if (res.status === 404) return null;
      throw await toApiError(res, `Failed to fetch briefing: ${res.statusText}`);
    }
    return res.json();
  },

  healthCheck: async () => {
    const res = await fetch(`${PROXY_BASE}/health`);
    if (!res.ok) throw await toApiError(res, "Backend not healthy");
    return res.json();
  },

  getCurrentUser: async (): Promise<CurrentUser> => {
    const res = await fetch(`${PROXY_BASE}/me`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to fetch current user: ${res.statusText}`);
    }
    return res.json();
  },

  submitAction: async (payload: ActionRequest): Promise<ActionRecord> => {
    const res = await fetch(`${PROXY_BASE}/actions`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to submit action: ${res.statusText}`);
    }
    return res.json();
  },

  getActions: async (exceptionId: string): Promise<ActionRecord[]> => {
    const res = await fetch(`${PROXY_BASE}/actions/${exceptionId}`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to fetch actions: ${res.statusText}`);
    }
    return res.json();
  },

  retryAction: async (requestId: string): Promise<ActionRecord> => {
    const res = await fetch(`${PROXY_BASE}/actions/${requestId}/retry`, {
      method: "POST",
      headers: JSON_HEADERS,
    });
    if (!res.ok) {
      throw await toApiError(res, `Failed to retry action: ${res.statusText}`);
    }
    return res.json();
  },
};
