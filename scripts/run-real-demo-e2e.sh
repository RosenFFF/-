#!/usr/bin/env bash
# Demo-ready real-backend e2e using the IN-REPO fixture (web/e2e/real-backend-fixture).
# Stand-ins: SQLite + fakeredis; tenant gate ON; vite DEV server; n=1 per viewport.
# Usage: BACKEND_DIR=<checkout@a437305>/backend scripts/run-real-demo-e2e.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$REPO/web"
FIX="$WEB/e2e/real-backend-fixture"
: "${BACKEND_DIR:?set BACKEND_DIR to <checkout@a437305>/backend}"
export BACKEND_DIR
export FIXTURE_STATE_DIR="${FIXTURE_STATE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/st143-real-fixture.XXXX")}"
export FIXTURE_RL_DEFAULT_PER_MIN="${FIXTURE_RL_DEFAULT_PER_MIN:-30}"
export DEMO_SAMPLE_PDF="$FIXTURE_STATE_DIR/sample-invoice.pdf"
LOG="$FIXTURE_STATE_DIR/logs"; mkdir -p "$LOG"
cleanup() { pkill -f 'serve_fixture:app' 2>/dev/null || true; [ -n "${VITE_PID:-}" ] && kill "$VITE_PID" 2>/dev/null || true; }
trap cleanup EXIT
restart_backend() {
  pkill -f 'serve_fixture:app' 2>/dev/null || true
  sleep 1
  M2_FRESH=1 "$FIX/start.sh" > "$LOG/backend.log" 2>&1 &
  for _ in $(seq 1 120); do
    curl -sf http://127.0.0.1:8000/api/v1/readyz >/dev/null && return 0
    sleep 0.5
  done
  echo "backend failed" >&2; tail -40 "$LOG/backend.log" >&2; exit 1
}
(cd "$WEB" && env -u VITE_USE_MOCK npx vite --port 5173 --strictPort > "$LOG/vite.log" 2>&1) &
VITE_PID=$!
for _ in $(seq 1 80); do curl -sk https://localhost:5173/ >/dev/null && break; sleep 0.25; done
for size in 390 1440; do
  restart_backend
  (cd "$WEB" && npx playwright test -c playwright.real-demo.config.ts --project="$size")
done
pkill -f 'vite.*5173' 2>/dev/null || true
echo "real-demo e2e done (state: $FIXTURE_STATE_DIR)"
