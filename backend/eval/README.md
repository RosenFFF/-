# Synthetic mini-eval (opt-in, one round)

`synthetic.py:samples()` deterministically generates the 20 labels in `labels.json`.
Images are rendered at run time by `tests.samples.invoice_image(lines=...)`:
8 clean, 3 missing origin, 3 malformed HS, 3 amount mismatch, 3 synthetic restricted goods.
All nine keys are scored with literal exact matching (no case/number normalization).
Missing origin is scored as an explicit null, not silently removed from the denominator.

Expected rule sets always include SYN-REVIEW. Finding scoring is the unique cited-rule
set per report, including model-added findings: intersection = hit, unexpected = false
positive, expected absent = miss. This is NOT an expert-labelled legal benchmark.

Run `RUN_EVAL_E2E=1 EVAL_PROVIDER=deepseek EVAL_EVIDENCE_DIR=<private-local-dir>
python -m pytest -q tests/test_backend_mini_eval.py` from backend, with credentials
injected only into the child environment using the machine-local private runner.
For L2 use `EVAL_PROVIDER=ollama` (cloud credentials explicitly absent); optional
`EVAL_OLLAMA_MODEL=qwen2.5:7b`. Defaults: 120s provider timeout, no retries,
300s chat generation deadline, 5s model health timeout. No security gates bypassed.

The fixture creates/drops a UUID-named PostgreSQL schema, migrates with the owner,
grants the distinct non-owner runtime role, and starts a private loopback Redis
process on an ephemeral port. No shared Redis DB or API listener is used.

DeepSeek: exactly 20 upload/review operations, and short chat on first 3 samples.
Ollama: 1 full login/upload/review/chat flow. Default pytest skips all paid/live calls.
The ASGI send observer measures actual application SSE frame emission, not httpx's
buffered ASGITransport response time. Application validation intentionally buffers
model output: first public delta can be almost simultaneous with done. These are
server-side ASGI timings, not network/client-perceived timings. Nearest-rank P95;
for 20 observations it is rank 19, for 3 it is rank 3.

`metrics.json` persists counts/timings/provenance only, never field values or prose.
A successful harness run is not an assertion that all outputs are accurate or L0:
consult recognition/review levels and successful provider traces for every sample.

Local minimal trial: EVAL_LOCAL_MINIMAL=1 selects a 3-line synthetic invoice (3 visible fields, missing required HS/origin), preserving the real OCR/extraction/review/SSE path. This is not the 20-sample accuracy dataset.

## Scope-aware correction / offline attribution

The original 32 hit / 89 extra / 0 miss scorer included SYN-REVIEW on both sides.
It therefore contributed 20 hits and **zero** extras. The corrected eligible
metric excludes that scope ID from both sides: **12 hit / 89 extra / 0 miss**.
Do not call every extra a genuine false positive. See
`reports/progress/backend-eval-extra-hits.md` for the irrecoverable historical
ledger gap and explicitly bounded, non-observed source attribution.

Future authorized runs now retain per-sample finding metadata (rule IDs, provenance,
severity, field keys), expected rule IDs and mismatching field keys — never field
values or prose. Legacy aggregate counts remain alongside corrected counts.
`eval.finding_metrics.attribute_ledger` reproduces exact per-rule source buckets
from such a ledger; duplicated sample IDs and unknown provenance fail closed.
No new model evaluation was performed for this correction.
