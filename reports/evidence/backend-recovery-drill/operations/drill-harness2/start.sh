#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR=/workspace/competition/live-deepseek-c75f877-src/backend
[ "$(git -C "$BACKEND_DIR" rev-parse HEAD)" = c75f877e09decd1b598c26f25e6b70e8742660d7 ]
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR:$ROOT"
exec /workspace/competition/live-deepseek-71311f4-src/backend/.venv/bin/python -m uvicorn serve_live_pg:app --host 127.0.0.1 --port 8003 --no-access-log
