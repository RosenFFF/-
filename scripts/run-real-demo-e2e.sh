#!/usr/bin/env bash
# Demo-ready real-backend e2e: backend code main a437305 via m2-real-backend fixture
# (SQLite + fakeredis stand-ins, tenant gate on). No secrets printed.
set -euo pipefail
WEB=/workspace/competition/st143-frontend/web
ROOT=/workspace/competition/m2-real-backend
export FIXTURE_RL_DEFAULT_PER_MIN="${FIXTURE_RL_DEFAULT_PER_MIN:-30}"
restart_backend() {
  pkill -f 'serve_fixture:app' 2>/dev/null || true
  sleep 1
  M2_FRESH=1 "$ROOT/start.sh" > /tmp/demo-backend.log 2>&1 &
  for _ in $(seq 1 60); do
    curl -sf http://127.0.0.1:8000/api/v1/readyz >/dev/null && return 0
    sleep 0.5
  done
  echo "backend failed" >&2; tail -40 /tmp/demo-backend.log >&2; exit 1
}
pkill -f 'vite.*5173' 2>/dev/null || true
sleep 1
(cd "$WEB" && env -u VITE_USE_MOCK npm run dev -- --port 5173 --strictPort > /tmp/demo-vite.log 2>&1 &)
for _ in $(seq 1 40); do curl -sk https://localhost:5173/ >/dev/null && break; sleep 0.25; done
for size in 390 1440; do
  restart_backend
  (cd "$WEB" && npx playwright test -c playwright.real-demo.config.ts --project="$size")
done
pkill -f 'vite.*5173' 2>/dev/null || true
echo "real-demo e2e done"
