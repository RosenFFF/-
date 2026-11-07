# Real-backend fixture (demo-ready e2e)

> **Label:** dev server (vite), SQLite/fakeredis stand-ins, n=1 per viewport; **not** production performance or full-stack acceptance.

This fixture serves the **real backend code at `a437305`** from a separate checkout, for `e2e/real-demo.spec.ts`.

## Expected environment

| Item | Value |
|---|---|
| Backend code | checkout at `a437305` (`backend/`) |
| Database | SQLite file in `$FIXTURE_STATE_DIR` (**stand-in**, not Postgres) |
| Redis | `fakeredis` in-process (**stand-in**, not Redis) |
| Tenant gate | **ON**. Existence check via `maintenance_sessionmaker` → `tests.conftest._seed` (tenant_session). No unscoped COUNT. |
| LLM chain | `deepseek, qwen, ollama`. DeepSeek/Qwen keys are **unset**. Ollama at `127.0.0.1:11434` is expected to have **no models** or not be running. Expect `degrade_level: L3` with every LLM `healthy: false`. The follow-up SSE should be HTTP 200 with only `event: error` (503 `MODEL_UNAVAILABLE`). The spec probes this and saves `models-probe-*.json`. |
| Sample document | synthetic, generated from backend `tests.samples.invoice_pdf()` |
| Accounts | synthetic `tests.conftest` fixture accounts (reviewer/admin), not real users |

The Ollama model names (`qwen2.5:7b` in a437305 config, `qwen2.5:0.5b` in backend 831cbe8 `model-probe.json`) are **configured names only**. They don't mean the model is installed or that inference succeeded. Only `healthy` status plus real call evidence count.

## Dependencies (as verified)

- **Backend:** Python 3.12 (backend `requires-python >=3.12,<3.13`) and `uv`. Install the backend deps from its `pyproject.toml`/`uv.lock` with the dev group (`fakeredis`, `pytest`) via `uv sync --group dev`.
- **Frontend:** Node 24 (verified v24.22.1) and npm. Install web deps with `npm ci`, then Playwright Chromium (`npx playwright install chromium`).
- `curl`.

## Env vars (placeholders only)

| Name | Required | Example / default |
|---|---|---|
| `BACKEND_DIR` | yes | `/path/to/backend-a437305/backend` |
| `BACKEND_PYTHON` | no | `$BACKEND_DIR/.venv/bin/python` |
| `FIXTURE_STATE_DIR` | no | runner: `mktemp -d $TMPDIR/st143-real-fixture.XXXX` |
| `FIXTURE_RL_DEFAULT_PER_MIN` | no | `30` (runner) / `2` (fixture) |
| `FIXTURE_OLLAMA_URL` | no | `http://127.0.0.1:11434` |
| `FIXTURE_PORT` | no | `8000` |
| `DEMO_SCREENSHOT_DIR` | no | `<repo>/../screenshots/demo-ready/` |
| `DEMO_SAMPLE_PDF` | set by runner | `$FIXTURE_STATE_DIR/sample-invoice.pdf` |
| `JWT_SECRET`, `DATA_KEK` | **never set by hand** | generated per run into `$FIXTURE_STATE_DIR/.env` (0600, outside the repo) |

## TLS

`vite.config.ts` uses `@vitejs/plugin-basic-ssl`. On the first `vite` start it generates a self-signed localhost cert under `node_modules/.vite`, which is never committed. Playwright uses `ignoreHTTPSErrors`. The backend serves plain HTTP on 127.0.0.1 behind the vite `/api` proxy. `cookie_secure=True` works because the browser sees HTTPS.

## Reproduce from the bundle

The bundle is thin (prerequisite `a437305`), so fetch it into a clone that already has `a437305`:

```bash
git clone <repo-with-a437305> fe && cd fe
git fetch /path/feat-frontend-demo-ready.bundle feat/frontend-demo-ready:feat/frontend-demo-ready && git checkout feat/frontend-demo-ready
git worktree add --detach /tmp/be-a437305 a437305 && (cd /tmp/be-a437305/backend && uv sync --group dev)
(cd web && npm ci && npx playwright install chromium)
BACKEND_DIR=/tmp/be-a437305/backend DEMO_SCREENSHOT_DIR=/tmp/demo-shots scripts/run-real-demo-e2e.sh
```

To start the fixture alone: `BACKEND_DIR=... M2_FRESH=1 web/e2e/real-backend-fixture/start.sh`.

`m2-real-backend-fixture.patch` is a redacted archive of the earlier out-of-repo fixture changes. You don't need it to reproduce the run.
