# ST-143 backend evaluation + Ollama offline degradation

## Positioning

**DeepSeek 为主，本地 qwen2.5:7b 作为 L2 离线降级**。CPU local inference is
not the interactive primary path. No stand-in inference is counted as real-model evidence.
The baseline is `6cba58f` (includes merged chat fix `71311f4`); branch
`feat/backend-eval-ollama`. No remote push and no protected process restart/stop.

## Probe hardening and transient L3

Coordinator-provided incident evidence: at approximately **2026-11-06 23:06 PST
(America/Tijuana)** the 8002 server logged cloud model-list GET 200 but no subsequent
alias-check POST completion. The configured alias is absent from model-list output;
`_probe` therefore performs a one-token alias POST. Its old one-second timeout could
expire, caught silently, marking health false for the 15-second cache. Circuit was
not open; the key was correctly injected (account check 200 / available). Ollama had
no installed model then, so all providers appeared unhealthy and the API reported L3.
The next probe recovered without restart. This is the coordinator's correlated
log diagnosis, not a newly reproduced outage or a definitive packet-level proof.

This bundle raises the default probe timeout to **4 seconds**, preserving the <=5s
validation bound and using the same timeout for list and alias calls. Probe failures
emit a constant structured warning with provider, stage (`list_models`/`alias_check`),
and exception class ONLY; no exception message, traceback, body, headers, or key.
Mock-transport tests cover alias timeout, alias success, and list failure, including
secret exclusion. Recommendation: deploy/configure 3-5 seconds for cloud alias checks.
With the model installed, a cloud health blip can select L2 instead of L3, provided
Ollama health and its circuit remain available; health is not an inference guarantee.

## Execution / credential boundary

Machine-only injector reuses `/workspace/competition/chat-sse-evidence-aaee76a/run.py`:
reads the specified secret file and private runtime JSON without printing values,
passes them exclusively into a subprocess environment, captures output, redacts
secrets and omits DSN/URL-bearing log lines. Neither private file is committed.
No public listener: in-process ASGI, UUID-isolated PG schema, separate non-owner
runtime role (FORCE RLS), ephemeral loopback-only Redis fixture, unchanged security gates.
Existing API/Ollama/PG/Redis processes are untouched, including obsolete 8001.

Commands (from worktree/backend):
```sh
PY=/workspace/competition/live-deepseek-71311f4-src/backend/.venv/bin/python
INJECT=/workspace/competition/ollama-eval-71311f4/run_private.py
python3 "$INJECT" ollama /workspace/competition/ollama-eval-71311f4/backend-7b
python3 "$INJECT" deepseek /workspace/competition/backend-mini-eval-71311f4
python3 "$INJECT" regression /workspace/competition/ollama-eval-71311f4/regression
# Injector selects: $PY -m pytest -q -p no:cacheprovider tests/test_backend_mini_eval.py
# or the complete suite, with RUN_*E2E removed for regression.
ruff check backend
bandit -r backend/app -q
gitleaks detect --no-git --source . --redact
```

## Model installation provenance

Prior operator state: binary `/workspace/tools/ollama-m1b/bin/ollama` v0.40.14,
model store `/workspace/tools/ollama-m1b/models`, qwen2.5:7b ID `845dbda0ea48`, ~4.7GB.
The native pull rejected the R2 blob redirect because the machine's DNS resolved
the target to 198.18.0.1 (non-public). **No redirect guard or TLS checks were disabled.**
Official registry manifest plus five blobs were downloaded by curl with sha256 and
size verification; staging script `staging-qwen2.5-7b/fetch.sh`, log `fetch.log`, manifest
`manifest.json` under that tools directory. Download uses a registry 307 to Cloudflare
R2; signed query strings are intentionally omitted. The independent verification
in `ollama-eval-71311f4/model-provenance.json` records the served manifest SHA256,
all five blob SHA256 digests and sizes, source manifest/blob URLs, and verification flags.
Prior direct inference: 24-token /api/chat, temperature 0, stop, 8.56s (operator-reported;
not backend acceptance). Backend evidence is reported separately below.

## Results

### Real DeepSeek — exactly one 20-sample round

- Completed 20/20; recognition L0 20/20, report L0 20/20, DeepSeek successful provider
  20/20; non-L0 reports **0** (no degraded output counted as L0).
- Literal field exact matches **157/180**. Per-field correct/total:

| Field | Correct / total |
|---|---:|
| invoice_no | 15/20 |
| total_amount | 20/20 |
| currency | 20/20 |
| hs_code | 20/20 |
| origin_country | 20/20 |
| quantity | 20/20 |
| unit_price | 20/20 |
| goods_description | 6/20 |
| consignee | 16/20 |

- Unique cited-rule scoring: **32 expected hits / 89 false-positive citations / 0 misses**.
  High extra-citation count is a real result, NOT hidden as perfect finding accuracy.
  Expected hits include deterministic rule-engine results; this is full-pipeline
  rule recall, NOT independent proof that the model discovered each anomaly.
- Upload→completed report (20): **P50 10402ms / P95 12046ms / max 12363ms**.
- Short chat subset (first 3/20): **3 completed, 3 DeepSeek**, each 1 delta + 1 done,
  no error; no citations were emitted for the destination-country question (not a
  citation-coverage test). First-delta **P50 1219ms / P95=max 1309ms**;
  done **P50 1219ms / P95=max 1309ms**. Public output is buffered for security checks.
- Raw counts/timings/provenance: `/workspace/competition/backend-mini-eval-71311f4/metrics.json`.
  The initial runner used a nonexistent trace `duration_ms` key, leaving that optional
  per-provider timing null in this artifact; corrected to `latency_ms` in delivered
  runner. End-to-end and SSE timings above were independently measured and unaffected.
  No paid rerun was performed merely to populate optional trace timing.

### Local Ollama

First full flow (qwen2.5:7b, 9-field invoice, provider timeout 120s, no retries):
`/system/models` reported **L2**, Ollama healthy; cloud keys absent. Login succeeded.
Upload/extraction **121609ms**, upload→completed rules report **241941ms**.
Both field extraction and compliance inference failed; recognition/report were **L3**,
0 grounded LLM fields, llm_verified=false. Chat emitted **1 error, 0 delta/citation/done**.
Total pytest wall time **272.67s**. This is **fallback/failure evidence only**, not proof
of L2 full inference. Initial optional trace duration fields were null (see above);
phase timings closely match the 120s per-call cap but failure traces do not expose
exception classes, so timeout is strongly indicated, not separately instrumented.

The installed model and successful 24-token direct request do NOT establish a usable
backend path. A smaller official qwen2.5:3b is therefore being tried with the same
integrity/security boundaries and the same 120s timeout cap. The requested positioning
remains the deployment goal; actual local qualification is reported honestly below.


## Limitations / metric definitions

The only dataset is 20 explicitly synthetic generated commercial-invoice images;
8 clean + 3 each missing-origin, malformed-HS, amount-mismatch, restricted-marker.
No real persons/businesses, legal accuracy claim, broad OCR generalization, or
production/load/concurrency guarantee. Single CPU machine (8 cores, ~12GB available RAM).
DeepSeek exactly ONE round, no whole-set reruns; chat only first 3/20 samples.
The label set/generator and opt-in test are committed; images regenerate on demand.
Nine literal field checks per sample include explicit nulls for missing labels.
Rule hits/FP/misses compare unique cited rule IDs per report, including informational
model-added citations, against labels. This is stricter than checking only anomaly
rules; unexpected citations count even if plausible general guidance. No prose/doc
content is persisted in reports. Exact-match does not normalize spaces, numeric
format or case. See `backend/eval/README.md` for full scoring semantics.
Nearest-rank P50/P95/max: P95 is 19th of 20; chat P95 is max of only 3, not stable.
First-delta/done timings are actual server ASGI send events (not network/client RTT
or provider TTFT). Chat output is security-validated before release, so these can
be nearly equal. Main timings include real OCR, DB/audit, extraction and reasoning.
