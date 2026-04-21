import type { NextConfig } from "next";

/**
 * Map root-level env vars (API_*) into Next.js NEXT_PUBLIC_* at dev/build time.
 *
 * This is how the project avoids a second `frontend/.env.local` file.
 * All credentials live in the root `.env` — one file for the whole stack.
 *
 * How it works:
 *   - `scripts/dev.sh` sources the root `.env` and starts `npm run dev` with
 *     those vars already in the shell environment.
 *   - Next.js then executes this config; `process.env.API_*` is already set.
 *   - The `env` block below re-exports them as `NEXT_PUBLIC_*` so they are
 *     inlined into the browser bundle (Next.js only exposes vars explicitly
 *     listed in `env` or prefixed `NEXT_PUBLIC_` to client-side code).
 *
 * Precedence (highest first):
 *   1. NEXT_PUBLIC_* already in env (allows overriding per-machine if needed)
 *   2. API_* from the root .env (the normal case — dev.sh injects these)
 *   3. Safe development fallbacks
 */
const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ||
      process.env.API_URL ||
      "http://localhost:8000",

    NEXT_PUBLIC_API_USERNAME:
      process.env.NEXT_PUBLIC_API_USERNAME ||
      process.env.API_USERNAME ||
      "admin",

    NEXT_PUBLIC_API_PASSWORD:
      process.env.NEXT_PUBLIC_API_PASSWORD ||
      process.env.API_PASSWORD ||
      "",
  },
};

export default nextConfig;
