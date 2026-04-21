import type { NextConfig } from "next";

// API_URL, API_USERNAME, API_PASSWORD are read server-side only by the
// /api/proxy route handler. They must NOT be exposed to the browser bundle.
// The single-source-of-truth root .env is sourced by scripts/dev.sh before
// starting the Next.js dev server, so no frontend/.env.local is needed.
const nextConfig: NextConfig = {};

export default nextConfig;
