# ST-143 backend evaluation + Ollama offline degradation

## Positioning

**云模型（DeepSeek）为主、规则引擎降级**（见下文 Formal decision；原定「本地 qwen2.5:7b 作为 L2」实测未达标，统筹于 2026-11-07 确认改定）。CPU local inference is
not the interactive primary path. No stand-in inference is counted as real-model evidence.
Initial worktree baseline was `6cba58f` (includes merged chat fix `71311f4`).
Before delivery the unpublished branch was rebased onto locally available **`905349c`**
(frontend/LICENSE-only changes; backend tree identical), with no fetch or remote push.
Final bundle prerequisite/base is **`905349c`**; branch
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
EVAL_OLLAMA_MODEL=qwen2.5:3b python3 "$INJECT" ollama /workspace/competition/ollama-eval-71311f4/backend-3b
EVAL_LOCAL_MINIMAL=1 python3 "$INJECT" ollama /workspace/competition/ollama-eval-71311f4/backend-7b-minimal-valid
python3 "$INJECT" regression /workspace/competition/ollama-eval-71311f4/regression-rebased
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
backend path. A smaller official qwen2.5:3b was therefore tried with the same
integrity/security boundaries and the same 120s timeout cap. The requested positioning
remains the deployment goal; actual local qualification is reported honestly below.

Second full flow (official qwen2.5:3b): login and L2 healthy probe succeeded.
Upload/extraction **48134ms**, field-inference trace **46950ms failed**, 0 grounded LLM
fields, recognition **L3**. Review inference **61076ms succeeded via Ollama**, report
**L2**, llm_verified=true, upload→report **109356ms**. Chat **1 delta + 1 citation +
1 done**, first-delta **28442ms**, done **28443ms**, successful provider Ollama,
delta text matched done. Total pytest wall time **141.016s**. This is genuine local
reasoning/chat evidence, but **NOT complete extraction→review L2 acceptance**:
field extraction used the rules fallback. Trace does not distinguish schema/output
rejection from other failure classes, so no unsupported root-cause claim is made.
Evidence `backend-3b/metrics.json`; all five 3b blobs verified by size+SHA256.

Third flow, qwen2.5:7b on a minimal three-line synthetic invoice: login and L2 probe
succeeded. Extraction **62429ms** (model trace **61949ms**) genuinely completed at
**L2**, with **3 grounded LLM fields**. Review inference failed at **120112ms**;
upload→rules report **182705ms**, report **L3**, llm_verified=false. Chat genuinely
completed via Ollama with **4 delta + 1 citation + 1 done**, first-delta/done both
**36098ms**, concatenated deltas equal done. Total pytest **221.918s**. Thus 7b is
proven to do backend extraction and validated/cited SSE, **but not the complete
extraction→LLM review→chat acceptance under the 120s cap**. Individual successes
from different runs/models are NOT spliced into a fictional full-flow pass.
Fourth flow, qwen2.5:3b minimal invoice: upload/extraction **5074ms**, field-inference
trace **4618ms failed**, recognition **L3**, 0 grounded LLM fields. Real review
inference **18016ms**, report **L2**, llm_verified=true, upload→report **23223ms**.
Real cited chat **1 delta + 1 citation + 1 done**, first-delta **20926ms**, done
**20927ms**, delta concatenation matches done. Total pytest **47.295s**. Again this
is partial real reasoning/chat plus rule-extraction fallback, NOT complete L2.
No further paid DeepSeek calls or local qualification retries are made.

### Formal decision: 「云模型为主、规则引擎降级」

Requested deployment positioning: **「DeepSeek 为主，本地 qwen2.5:7b 作为 L2 离线降级」**.
The second half is an **unqualified target, not a completed full-flow claim** on this
machine/configuration. Full L2 acceptance failed in all four completed trials:
7b nine-field extraction/reasoning exceeded the observed 120s budgets; minimal 7b
extraction succeeded but reasoning failed at 120112ms. Both 3b trials produced real
review/chat, but extraction failed before timeout, so neither satisfies complete
model extraction→model review→chat. No default timeout/security bound was bypassed.

Ship DeepSeek as the qualified primary. Treat the deterministic rule engine as the
qualified degraded review behavior; make L3/manual-review status explicit. The
existing Ollama chain may deliver partial L2 inference and validated cited chat,
but **do not promise a fully model-driven offline review** with the current 120s
cap/CPU/strict-output acceptance. Chat remains explicit error when inference is
unavailable (no fabricated rules-only assistant answer). Further qualification needs
controlled idle-machine/higher-throughput hardware and investigation of the safe
field-output failure classes before reconsidering the local-path SLA.
An accidental preparatory launch before the minimal-mode patch was applied was
cancelled via SIGINT to **only its own pytest child**; fixture cleanup ran. No result
from this aborted attempt is claimed; protected PIDs were never signalled.


## Limitations / metric definitions

The only dataset is 20 explicitly synthetic generated commercial-invoice images;
8 clean + 3 each missing-origin, malformed-HS, amount-mismatch, restricted-marker.
No real persons/businesses, legal accuracy claim, broad OCR generalization, or
production/load/concurrency guarantee. Single CPU machine (8 cores, ~12GB available RAM).
Live model trials overlapped some regression activity and may suffer CPU/resource
contention; these are observed per-run timings, not controlled idle-machine benchmarks.
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


## Regression / security

After rebasing onto `905349c`, complete backend regression with live PG injection:
**400 passed, 5 skipped, 221.28s**. Paid/live DeepSeek opt-ins remained skipped.
Initial pre-hardening pass was 397/5; pre-rebase hardened pass also completed.
Probe tests include default 4s/read-timeout assertion, alias success, alias timeout
and list failure with structured log-field checks and secret exclusion.
`ruff check backend`: passed. `bandit -r backend/app -q`: passed (production Python
scope; tests contain intentional assertions). Full-worktree gitleaks scan: 0 leaks.
Actual private-key byte comparison (in-process, value never emitted): 0 hits.
Final committed snapshot and evidence are rescanned before bundling.

## Delivery

One local bundle (no push):
```sh
git bundle create /workspace/competition/bundles/feat-backend-eval-ollama.bundle 905349c..feat/backend-eval-ollama
git bundle verify /workspace/competition/bundles/feat-backend-eval-ollama.bundle
sha256sum /workspace/competition/bundles/feat-backend-eval-ollama.bundle
```
This is an incremental bundle requiring commit `905349c`, not a standalone full clone.
Aggregate metrics/model hashes and regression output are included under
`reports/evidence/backend-eval-ollama/`, with SHA256SUMS. Machine-local evidence
roots: `/workspace/competition/ollama-eval-71311f4/` and
`/workspace/competition/backend-mini-eval-71311f4/`. Each has a README and SHA256SUMS.
Model weights and private runtime configuration are NOT in the bundle.
