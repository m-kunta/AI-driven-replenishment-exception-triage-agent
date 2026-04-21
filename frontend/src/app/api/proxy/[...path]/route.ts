import { type NextRequest, NextResponse } from "next/server";

/**
 * BFF proxy — reads API credentials server-side and forwards all requests to
 * the FastAPI backend. Credentials live in process.env (Node.js only) and are
 * never serialised into the client JS bundle.
 *
 * Env vars (server-side, NOT NEXT_PUBLIC_*):
 *   API_URL       FastAPI base URL  (default: http://localhost:8000)
 *   API_USERNAME  HTTP Basic user   (default: admin)
 *   API_PASSWORD  HTTP Basic pass   (required)
 */
const UPSTREAM = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");

function buildAuth(): string | null {
  const username = process.env.API_USERNAME ?? "admin";
  const password = process.env.API_PASSWORD ?? "";
  if (!password) return null;
  // Buffer (Node.js) — not btoa() — ensures this cannot run in a browser context
  return `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
}

async function handler(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const auth = buildAuth();
  if (!auth) {
    return NextResponse.json(
      {
        detail:
          "[Exception Copilot Proxy] API_PASSWORD is not set. " +
          "Start the stack with `bash scripts/dev.sh` to export the root .env.",
      },
      { status: 503 }
    );
  }

  const { path } = await params;
  const search = req.nextUrl.search;
  const url = `${UPSTREAM}/${path.join("/")}${search}`;

  const headers = new Headers({
    Authorization: auth,
    "Content-Type": "application/json",
  });

  const body =
    req.method !== "GET" && req.method !== "HEAD"
      ? await req.text()
      : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(url, { method: req.method, headers, body });
  } catch {
    return NextResponse.json(
      {
        detail: `[Exception Copilot Proxy] Backend unreachable at ${UPSTREAM}. Is uvicorn running?`,
      },
      { status: 502 }
    );
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as DELETE,
  handler as PATCH,
};
