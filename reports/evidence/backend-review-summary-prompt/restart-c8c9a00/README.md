# c8c9a00 loopback integration harness (not production/browser E2E)

Source: detached full commit c8c9a00009612a7fec60b44193795d9a9ac8180c,
/workspace/competition/live-deepseek-c8c9a00-src. start.sh checks the full hash.
Fresh random st143_dsc8_browser_* schema, real non-owner m3_runtime FORCE RLS,
real Redis DB12, inline tasks, real ProviderChain. Alembic and startup gates run
unchanged; no DROP/FLUSHDB, SQLite/fakeredis/model stand-in, or public listener.
Private config/key read into memory only; logs suppress DSN/URL lines and secrets.
environment-proof.json explicitly mode 600. Runtime keys are never written.

2026-11-07 02:09 PST (America/Tijuana): exact old 8002 PID539339 verified as
71311f4 uvicorn, SIGTERM and pidfd exit verified. Obsolete 8001 PID496807 verified
as aaee76a uvicorn, SIGTERM and exit verified. Existing harness directories/code
were not overwritten. New uvicorn PID1047443 listens only 127.0.0.1:8002.

Smoke: readyz200, Origin-protected synthetic login200, system/models200,
L0 and DeepSeek healthy. Readiness/models shared the 15-second health cache.
No upload/review/chat or paid inference beyond the health probe. Cookie values
stayed in the smoke process, never evidence. Server Secure-cookie configuration
was preserved; internal loopback HTTP represents the frontend proxy hop, not
browser HTTPS acceptance. No TLS verification was disabled. This server is pinned
to c8c9a00, NOT the later summary/prompt feature branch.

Evidence: process-restart.json, environment-proof.json (600), readyz.json,
system-models.json, smoke.json, SHA256SUMS. runtime/server.log is redacted;
runtime/server.pid records the actual uvicorn PID (the log pump has another PID).
Do not start another listener or re-run model health unnecessarily.
