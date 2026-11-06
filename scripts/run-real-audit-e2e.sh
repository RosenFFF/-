#!/usr/bin/env bash
set -euo pipefail
WEB=/workspace/competition/st143-frontend/web
ROOT=/workspace/competition/m2-real-backend
restart_backend() {
  pkill -f 'uvicorn.*8000|serve_fixture' 2>/dev/null || true
  sleep 1
  M2_FRESH=1 "$ROOT/start.sh" > /tmp/m2-backend.log 2>&1 &
  for i in $(seq 1 60); do
    curl -sf http://127.0.0.1:8000/api/v1/readyz >/dev/null && return 0
    sleep 0.5
  done
  echo "backend failed" >&2
  tail -40 /tmp/m2-backend.log >&2
  exit 1
}
# ensure vite
if ! curl -sk https://localhost:5173/ >/dev/null; then
  (cd "$WEB" && env -u VITE_USE_MOCK npm run dev -- --port 5173 --strictPort > /tmp/m2-vite.log 2>&1 &)
  for i in $(seq 1 40); do curl -sk https://localhost:5173/ >/dev/null && break; sleep 0.25; done
fi
restart_backend
(cd "$WEB" && npx playwright test -c playwright.real-audit.config.ts --project=390)
restart_backend
(cd "$WEB" && npx playwright test -c playwright.real-audit.config.ts --project=1440)
echo "real-audit e2e done"
