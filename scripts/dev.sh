#!/usr/bin/env bash
# =============================================================================
# dev.sh — Start the full Exception Copilot stack for local development
#
# Usage:  bash scripts/dev.sh [--no-frontend] [--no-backend]
#
# Single source of truth: the root .env file.
# No frontend/.env.local needed — next.config.ts reads API_* vars directly
# from the shell environment injected below.
# =============================================================================

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[dev]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[warn]${RESET} $*"; }
error() { echo -e "${RED}[error]${RESET} $*" >&2; }

# ── Parse flags ─────────────────────────────────────────────────────────────────
START_BACKEND=true
START_FRONTEND=true
for arg in "$@"; do
  case "$arg" in
    --no-frontend) START_FRONTEND=false ;;
    --no-backend)  START_BACKEND=false ;;
    *) warn "Unknown flag: $arg" ;;
  esac
done

# ── Resolve paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

# ── Step 1: Load and validate root .env ───────────────────────────────────────
ROOT_ENV="${ROOT_DIR}/.env"

if [[ ! -f "$ROOT_ENV" ]]; then
  warn ".env not found — creating from .env.example"
  cp "${ROOT_DIR}/.env.example" "$ROOT_ENV"
  error "Edit ${ROOT_ENV}: set API_PASSWORD (and your AI provider key), then re-run."
  exit 1
fi

# Export all vars from .env into the current shell
set -a
# shellcheck source=/dev/null
source "$ROOT_ENV"
set +a

# Validate the two required Web UI vars
if [[ -z "${API_PASSWORD:-}" || "${API_PASSWORD}" == "changeme" ]]; then
  error "API_PASSWORD is not set or still 'changeme' in ${ROOT_ENV}."
  error "Set it to a real password — both the backend and frontend will use it."
  exit 1
fi

info "Root .env loaded  ✓  (API_USERNAME=${API_USERNAME:-admin}, API_URL=${API_URL:-http://localhost:8000})"

# ── Step 2: Check Python venv ─────────────────────────────────────────────────
PYTHON="${ROOT_DIR}/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  error "Python venv not found at ${PYTHON}."
  error "Run:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# ── Step 3: Check frontend node_modules ───────────────────────────────────────
if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  info "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# ── Step 4: Launch services ───────────────────────────────────────────────────
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  info "Shutting down..."
  [[ -n "$BACKEND_PID" ]]  && kill "$BACKEND_PID"  2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null
  info "Done."
}
trap cleanup INT TERM EXIT

if [[ "$START_BACKEND" == true ]]; then
  info "Starting FastAPI backend  →  http://localhost:8000"
  (
    cd "$ROOT_DIR"
    export API_USERNAME="${API_USERNAME:-admin}"
    export API_PASSWORD="$API_PASSWORD"
    "$PYTHON" -m uvicorn src.api.app:app --reload --port 8000 --host 0.0.0.0
  ) &
  BACKEND_PID=$!
fi

if [[ "$START_FRONTEND" == true ]]; then
  info "Starting Next.js frontend  →  http://localhost:3000"
  # API_* vars are already exported — next.config.ts maps them to NEXT_PUBLIC_*
  (
    cd "$FRONTEND_DIR"
    npm run dev
  ) &
  FRONTEND_PID=$!
fi

# ── Banner ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}┌─────────────────────────────────────────────────┐${RESET}"
echo -e "${GREEN}│  Exception Copilot — dev stack running           │${RESET}"
echo -e "${GREEN}├─────────────────────────────────────────────────┤${RESET}"
[[ "$START_BACKEND" == true ]]  && \
  echo -e "${GREEN}│  Backend   →  http://localhost:8000              │${RESET}"
[[ "$START_FRONTEND" == true ]] && \
  echo -e "${GREEN}│  Frontend  →  http://localhost:3000              │${RESET}"
echo -e "${GREEN}│  API Docs  →  http://localhost:8000/docs         │${RESET}"
echo -e "${GREEN}└─────────────────────────────────────────────────┘${RESET}"
echo ""
echo "  Press Ctrl-C to stop all services."
echo ""

wait
