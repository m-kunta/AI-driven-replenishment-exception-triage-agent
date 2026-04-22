/**
 * @jest-environment node
 */
/**

 * Tests for the BFF proxy Route Handler.
 *
 * Strategy
 * --------
 * The Route Handler reads server-side env vars and calls the upstream FastAPI.
 * We test it in a Node.js-like environment by:
 *
 *   1. Mocking `next/server` — NextRequest / NextResponse are thin wrappers
 *      that Jest can stub without a real Next.js runtime.
 *   2. Mocking global `fetch` — prevents real network calls.
 *   3. Controlling `process.env.API_PASSWORD` per test to exercise the
 *      missing-password 503 guard.
 *
 * The module is re-imported after each env mutation (jest.resetModules) to
 * pick up the new process.env values, since UPSTREAM and buildAuth() read
 * env at module load time.
 */

import { NextResponse } from "next/server";

// ---------------------------------------------------------------------------
// Helpers — build minimal NextRequest-like objects
// ---------------------------------------------------------------------------

function makeRequest(
  method = "GET",
  path = "/health",
  body?: string,
  search = ""
): {
  method: string;
  nextUrl: { search: string };
  text: () => Promise<string>;
} {
  return {
    method,
    nextUrl: { search },
    text: async () => body ?? "",
  };
}

function makeParams(segments: string[]): Promise<{ path: string[] }> {
  return Promise.resolve({ path: segments });
}

// ---------------------------------------------------------------------------
// Shared mock state
// ---------------------------------------------------------------------------

const savedEnv = process.env;

beforeEach(() => {
  jest.resetModules();
  process.env = { ...savedEnv };
  (global.fetch as jest.Mock) = jest.fn();
});

afterEach(() => {
  process.env = savedEnv;
});

// ---------------------------------------------------------------------------
// 503 — missing API_PASSWORD
// ---------------------------------------------------------------------------

describe("proxy route — 503 when API_PASSWORD missing", () => {
  beforeEach(() => {
    delete process.env.API_PASSWORD;
  });

  it("returns 503 status", async () => {
    const { GET } = await import("./route");
    const req = makeRequest("GET", "/health");
    const res = await GET(req as never, { params: makeParams(["health"]) });
    expect(res.status).toBe(503);
  });

  it("includes an actionable error message", async () => {
    const { GET } = await import("./route");
    const req = makeRequest("GET", "/health");
    const res = await GET(req as never, { params: makeParams(["health"]) });
    const body = await res.json();
    expect(body.detail).toMatch(/API_PASSWORD/);
    expect(body.detail).toMatch(/dev\.sh/);
  });

  it("does not call fetch when password is missing", async () => {
    const { GET } = await import("./route");
    const req = makeRequest("GET", "/health");
    await GET(req as never, { params: makeParams(["health"]) });
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// 502 — upstream unreachable
// ---------------------------------------------------------------------------

describe("proxy route — 502 when upstream is unreachable", () => {
  beforeEach(() => {
    process.env.API_PASSWORD = "testpass";
    (global.fetch as jest.Mock).mockRejectedValue(new Error("ECONNREFUSED"));
  });

  it("returns 502 status", async () => {
    const { GET } = await import("./route");
    const req = makeRequest("GET", "/health");
    const res = await GET(req as never, { params: makeParams(["health"]) });
    expect(res.status).toBe(502);
  });

  it("includes backend unreachable message", async () => {
    const { GET } = await import("./route");
    const req = makeRequest("GET", "/health");
    const res = await GET(req as never, { params: makeParams(["health"]) });
    const body = await res.json();
    expect(body.detail).toMatch(/unreachable/i);
  });
});

// ---------------------------------------------------------------------------
// Happy path — GET forwarding
// ---------------------------------------------------------------------------

describe("proxy route — GET happy path", () => {
  beforeEach(() => {
    process.env.API_PASSWORD = "testpass";
    process.env.API_USERNAME = "admin";
    process.env.API_URL = "http://localhost:8000";
  });

  function mockUpstream(body: string, status = 200, contentType = "application/json") {
    (global.fetch as jest.Mock).mockResolvedValue({
      status,
      text: async () => body,
      headers: { get: (h: string) => (h === "Content-Type" ? contentType : null) },
    });
  }

  it("calls fetch with correct upstream URL", async () => {
    mockUpstream('{"status":"ok"}');
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    await GET(req as never, { params: makeParams(["health"]) });
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.anything()
    );
  });

  it("injects Authorization header with base64 credentials", async () => {
    mockUpstream('{"status":"ok"}');
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    await GET(req as never, { params: makeParams(["health"]) });
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    const authHeader = options.headers.get("Authorization");
    // admin:testpass → YWRtaW46dGVzdHBhc3M=
    expect(authHeader).toBe(
      `Basic ${Buffer.from("admin:testpass").toString("base64")}`
    );
  });

  it("forwards the upstream response status", async () => {
    mockUpstream('{"run_dates":[]}', 200);
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    const res = await GET(req as never, { params: makeParams(["runs"]) });
    expect(res.status).toBe(200);
  });

  it("forwards 404 from upstream as-is", async () => {
    mockUpstream('{"detail":"not found"}', 404);
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    const res = await GET(req as never, { params: makeParams(["briefing", "2026-04-20"]) });
    expect(res.status).toBe(404);
  });

  it("constructs nested path correctly", async () => {
    mockUpstream("[]");
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    await GET(req as never, {
      params: makeParams(["exceptions", "queue", "CRITICAL", "2026-04-20"]),
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/exceptions/queue/CRITICAL/2026-04-20",
      expect.anything()
    );
  });

  it("appends query string to upstream URL", async () => {
    mockUpstream("[]");
    const { GET } = await import("./route");
    const req = makeRequest("GET", "/runs", undefined, "?limit=10");
    await GET(req as never, { params: makeParams(["runs"]) });
    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/runs?limit=10",
      expect.anything()
    );
  });

  it("does not include a body for GET requests", async () => {
    mockUpstream("[]");
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    await GET(req as never, { params: makeParams(["runs"]) });
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.body).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Happy path — POST forwarding
// ---------------------------------------------------------------------------

describe("proxy route — POST happy path", () => {
  beforeEach(() => {
    process.env.API_PASSWORD = "testpass";
    process.env.API_URL = "http://localhost:8000";
    (global.fetch as jest.Mock).mockResolvedValue({
      status: 202,
      text: async () => '{"status":"queued"}',
      headers: { get: () => "application/json" },
    });
  });

  it("forwards POST body to upstream", async () => {
    const { POST } = await import("./route");
    const payload = JSON.stringify({ run_date: "2026-04-20", sample: true });
    const req = makeRequest("POST", "/pipeline/trigger", payload);
    await POST(req as never, { params: makeParams(["pipeline", "trigger"]) });
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.body).toBe(payload);
  });

  it("uses method=POST on the upstream call", async () => {
    const { POST } = await import("./route");
    const req = makeRequest("POST", "/pipeline/trigger", "{}");
    await POST(req as never, { params: makeParams(["pipeline", "trigger"]) });
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.method).toBe("POST");
  });

  it("returns 202 from upstream", async () => {
    const { POST } = await import("./route");
    const req = makeRequest("POST", "/pipeline/trigger", "{}");
    const res = await POST(req as never, { params: makeParams(["pipeline", "trigger"]) });
    expect(res.status).toBe(202);
  });
});

// ---------------------------------------------------------------------------
// Trailing slash stripping on API_URL
// ---------------------------------------------------------------------------

describe("proxy route — API_URL trailing slash handling", () => {
  it("strips trailing slash from API_URL before building upstream URL", async () => {
    process.env.API_PASSWORD = "testpass";
    process.env.API_URL = "http://localhost:8000/";
    (global.fetch as jest.Mock).mockResolvedValue({
      status: 200,
      text: async () => "{}",
      headers: { get: () => "application/json" },
    });
    const { GET } = await import("./route");
    const req = makeRequest("GET");
    await GET(req as never, { params: makeParams(["health"]) });
    const [url] = (global.fetch as jest.Mock).mock.calls[0];
    // Should NOT be http://localhost:8000//health
    expect(url).toBe("http://localhost:8000/health");
    expect(url).not.toContain("//health");
  });
});
