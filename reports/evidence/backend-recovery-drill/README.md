# Recovery drill: actual observations vs offline tests

See ../../progress/backend-recovery-drill.md, especially the temporary health-only guard limitation on current8002.
recovery-summary.json combines the complete Redis fault from attempt1 and PG/relay faults from attempt2; both source attempts preserved. HTTP null + transport_error means NO HTTP response, not a synthetic status. PG-down RLS unavailable is not a pass. L2 is actual provider-health availability, NOT full Ollama inference proof.
operations/: as-executed scripts and private-instance metadata; not automatic entry points. Credentials remain in process/child env, not files. Private PG data/auth files, Redis data and encrypted storage deliberately excluded.
restart-c75f877/: pinned8002 proofs/scripts. Actual environment-proof600; Git cannot preserve600. Current process still has strict temporary health-only transport; normal inference is blocked and future probes can hit budget. Do not mistake final L0 snapshot for unrestricted service readiness.
api*.redacted.log: URL/DSN lines suppressed and private values redacted. Observed c75 errors are pre-fix; new503 handler is validated only offline, not deployed.
SHA256SUMS covers stable files excluding itself. Final commit/bundle receipts live outside Git to avoid recursive checksums. Nothing pushed; shared services never restarted.
