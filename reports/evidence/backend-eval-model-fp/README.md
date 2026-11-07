# Single authorized ledgered DeepSeek capture, then OFFLINE replay

live/sample-01.json ... sample-20.json: atomically persisted metadata/booleans only.
No document text/values, model prose, credentials, actual balance, or document IDs.
accounting.json: 40 model requests (20 extraction + 20 review), 2 balance GETs,
0 chat. Consumed immediate balance delta 0.00 CNY; NOT a promise of free/unbilled
calls (API precision/settlement/account concurrency may affect the observation).
No actual before/after balances were serialized. model-call-counts.json is the
independent transport counter, persisted before/after every physical request.

replay.json: same captured inputs, production output filter, no model calls.
Scope excluded: before 12 hit/81 extra/0 miss, after 12/25/0. All 81 original
extra pairs are model generated; 55 are false synthetic-precondition alerts and
become 0. One mixed public citation disappears; 25 public advisory extras remain
unadjudicated, not silently called genuine FP or deleted to fake perfect accuracy.
The earlier historical 89 extras belong to a different run; this does not recover
that lost ledger. See reports/progress/backend-eval-model-fp.md for complete tables,
synthetic FP sample IDs, root causes, fix semantics and limitations.

Checksums are relative to this directory. Full regression 418 passed/6 skipped,
103.40s with every model opt-in disabled. No additional paid test or service restart.
