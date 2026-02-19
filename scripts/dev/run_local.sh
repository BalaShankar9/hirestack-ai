#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"

echo "[HireStack] Starting backend on http://localhost:${BACKEND_PORT} ..."
cd "${ROOT}/backend"
python3 -m uvicorn main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID="$!"

cleanup() {
  if kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    echo
    echo "[HireStack] Stopping backend (pid ${BACKEND_PID}) ..."
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[HireStack] Starting frontend on http://localhost:${FRONTEND_PORT} ..."
cd "${ROOT}/frontend"
echo
echo "[HireStack] Open in browser:"
echo "  http://localhost:${FRONTEND_PORT}/login"
echo
echo "[HireStack] (Stop with Ctrl+C)"
echo
npm run dev -- --hostname "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
