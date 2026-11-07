#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR=/workspace/competition/live-deepseek-c8c9a00-src/backend
[ "$(git -C "$BACKEND_DIR" rev-parse HEAD)" = c8c9a00009612a7fec60b44193795d9a9ac8180c ]
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR:$ROOT"
exec /workspace/competition/live-deepseek-71311f4-src/backend/.venv/bin/python -m uvicorn serve_live_pg:app --host 127.0.0.1 --port 8002 --no-access-log
