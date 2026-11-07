#!/usr/bin/env bash
# Start the real-backend fixture. Requires BACKEND_DIR = <backend checkout at a437305>/backend
# with deps installed: (cd "$BACKEND_DIR" && uv sync --group dev)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${BACKEND_DIR:?set BACKEND_DIR to <checkout@a437305>/backend}"
export FIXTURE_STATE_DIR="${FIXTURE_STATE_DIR:-${TMPDIR:-/tmp}/st143-real-fixture}"
PY="${BACKEND_PYTHON:-$BACKEND_DIR/.venv/bin/python}"
mkdir -p "$FIXTURE_STATE_DIR"
cd "$BACKEND_DIR"
export PYTHONPATH="$HERE:$BACKEND_DIR:${PYTHONPATH:-}"
# Synthetic sample invoice from the backend's own test helpers (no real documents).
"$PY" -c "import sys; from tests.samples import invoice_pdf; open(sys.argv[1],'wb').write(invoice_pdf())" "$FIXTURE_STATE_DIR/sample-invoice.pdf"
exec "$PY" -m uvicorn serve_fixture:app --host 127.0.0.1 --port "${FIXTURE_PORT:-8000}" --app-dir "$HERE"
