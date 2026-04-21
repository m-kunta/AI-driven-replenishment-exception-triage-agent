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

// All requests route through the Next.js server-side proxy at /api/proxy,
// which injects Basic Auth credentials from server-only env vars. No credential
// is ever sent to the browser.
const PROXY_BASE = "/api/proxy";

const JSON_HEADERS = { "Content-Type": "application/json" };

export const api = {
  triggerPipeline: async (payload: PipelineTriggerRequest) => {
    const res = await fetch(`${PROXY_BASE}/pipeline/trigger`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to trigger pipeline: ${res.statusText}`);
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
      throw new Error(`Failed to fetch queue: ${res.statusText}`);
    }
    return res.json();
  },

  getRuns: async (): Promise<string[]> => {
    const res = await fetch(`${PROXY_BASE}/runs`, {
      method: "GET",
      headers: JSON_HEADERS,
    });
    if (!res.ok) return [];
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
      throw new Error(`Failed to fetch briefing: ${res.statusText}`);
    }
    return res.json();
  },

  healthCheck: async () => {
    const res = await fetch(`${PROXY_BASE}/health`);
    if (!res.ok) throw new Error("Backend not healthy");
    return res.json();
  },
};
