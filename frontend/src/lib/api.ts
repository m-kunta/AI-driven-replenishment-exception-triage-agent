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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Env validation — surfaces misconfiguration as a clear error rather than a
// silent 401 that is hard to debug.
// ---------------------------------------------------------------------------

/**
 * Validates that the required frontend env vars are present and not still set
 * to the placeholder value from .env.local.example.
 *
 * Called lazily on first API request so it does not block SSR/build steps,
 * but fires immediately when the user's browser triggers any fetch.
 */
function validateEnv(): void {
  const password = process.env.NEXT_PUBLIC_API_PASSWORD;

  if (!password || password === "your_password_here") {
    throw new Error(
      "[Exception Copilot] NEXT_PUBLIC_API_PASSWORD is not configured.\n" +
        "Copy frontend/.env.local.example → frontend/.env.local and set " +
        "NEXT_PUBLIC_API_PASSWORD to match your backend API_PASSWORD env var, " +
        "then restart the dev server."
    );
  }
}

// Credentials sourced from .env.local — copy .env.local.example to .env.local before running
const getAuthHeaders = (): Record<string, string> => {
  validateEnv();
  const username = process.env.NEXT_PUBLIC_API_USERNAME ?? "admin";
  const password = process.env.NEXT_PUBLIC_API_PASSWORD ?? "";
  const credentials = btoa(`${username}:${password}`);
  return {
    Authorization: `Basic ${credentials}`,
    "Content-Type": "application/json",
  };
};

export const api = {
  triggerPipeline: async (payload: PipelineTriggerRequest) => {
    const res = await fetch(`${API_BASE_URL}/pipeline/trigger`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to trigger pipeline: ${res.statusText}`);
    }
    return res.json();
  },

  getQueue: async (priority: Priority, runDate: string): Promise<TriageResult[]> => {
    const res = await fetch(`${API_BASE_URL}/exceptions/queue/${priority}/${runDate}`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    if (!res.ok) {
      if (res.status === 404) return [];
      throw new Error(`Failed to fetch queue: ${res.statusText}`);
    }
    return res.json();
  },

  getRuns: async (): Promise<string[]> => {
    const res = await fetch(`${API_BASE_URL}/runs`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.run_dates ?? [];
  },

  getBriefing: async (runDate: string): Promise<{ run_date: string; content: string } | null> => {
    const res = await fetch(`${API_BASE_URL}/briefing/${runDate}`, {
      method: "GET",
      headers: getAuthHeaders(),
    });
    if (!res.ok) {
      if (res.status === 404) return null;
      throw new Error(`Failed to fetch briefing: ${res.statusText}`);
    }
    return res.json();
  },

  healthCheck: async () => {
    const res = await fetch(`${API_BASE_URL}/health`);
    if (!res.ok) throw new Error("Backend not healthy");
    return res.json();
  },
};
