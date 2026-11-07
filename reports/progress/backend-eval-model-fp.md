# ST-143: one authorized real DeepSeek capture + offline model-FP filtering

Base `fa06661` was already local; branch `feat/backend-eval-model-fp`. No remote
push, credential setup, or service restart. 8002, Ollama, PG and shared Redis were
untouched. Existing isolated FORCE-RLS runtime-role/schema and loopback Redis
fixtures were used; no production database rows or shared Redis DB were used.

## Exactly one paid-model run / accounting

- **20/20 completed**, extraction L0 20/20, review L0 20/20, provider DeepSeek.
- **40 model HTTP calls**: 20 field_extraction + 20 compliance_reasoning; all HTTP
  200. Zero retries, zero alias/health model calls, **zero chat**. Only DeepSeek was
  configured in this test; no stand-in/local model was used.
- **2 balance GET calls**, immediately before and after the loop; 42 outbound
  DeepSeek HTTP requests total. Key injected only into child env. Actual balances
  stayed in memory and were never printed, logged, serialized, or committed.
- Observed immediate account-balance difference: **0.00 CNY**. This is the returned
  endpoint's immediate delta, NOT proof that 40 calls were unbilled/free: precision,
  settlement delay or other account activity can affect the delta. No third balance
  query or paid retry was made to resolve this. No before/after balances are saved.
- Request transport enforces a hard 40-call budget, writing task/status counters
  before/after each request. An exclusive run-start marker prevents accidental
  whole-set reruns. No other paid test ran.
- Upload→report timings (20): **P50 7757ms / P95 9820ms / max 10004ms**, nearest-rank.
  These are BEFORE-filter real-run timings, not a new post-filter inference result.
  The counting transport uses a shared real HTTP connection pool; the default
  production chain creates clients per call. Instrumentation/fsync/connection reuse
  can affect timings, so these are not production SLA or filter-speedup claims.

The model ran against the original unfiltered review service imported from the
base, with capture-only hooks. The production filter was wired only after the
capture process imported/started the old service. No new model run used the fix.

## Immediate, value-free evidence persistence

Each sample is atomically written and fsynced at start, after extraction, at the
actual deterministic rule check BEFORE reasoning, and immediately after validated
model findings BEFORE review DB commit or HTTP response. Predicates are computed
from actual in-memory extracted fields by the existing deterministic engine, not
from labels or public-field-display guesses. Only boolean condition flags are saved.

Ledger fields: synthetic sample id, expected rule IDs, per-finding rule_ids,
determined_by, severity, category, field_keys; field_mismatch_keys, condition flags,
completion/degrade status, provider/task/status/timing. No document text, field
values, prompts, model prose, report/document IDs, or balances. All 20 ledgers were
captured; no partial/crashed sample. JSON capture survives fixture schema cleanup.

## Metric / exact bucket definitions

Count distinct **(synthetic sample id, cited rule id)** pairs, not finding objects.
Remove SYN-REVIEW from BOTH expected and actual sets; hit=intersection,
extra=actual-minus-expected, miss=expected-minus-actual. Do not discard every info
finding. Every extra is assigned once: deterministic producer takes precedence if
a rule has both model and rule producers; otherwise determined_by != rule is model.
An out-of-label public guidance citation is not automatically a factual/legal FP.

This NEW rerun has **81**, not the historical run's 89 extras. Historical 89 remains
unattributable; we do not retroactively replace its missing ledger with this run.
Here all **81/81** extras have exact saved provenance: scope-extra **0**, model
**81**, deterministic **0**. SYN-REVIEW has 20 excluded scope pairs, already expected.

| Rule ID | Excluded scope pairs | Model extra before | Deterministic extra before | Extra after | Proven model FP before → after |
|---|---:|---:|---:|---:|---|
| SYN-REVIEW | 20 | 0 | 0 | 0 | 0 → 0 |
| SYN-REQUIRED | 0 | 17 | 0 | 0 | 17 → 0 |
| SYN-HS | 0 | 2 | 0 | 0 | 2 → 0 |
| SYN-AMOUNT | 0 | 16 | 0 | 0 | 16 → 0 |
| SYN-RESTRICTED | 0 | 0 | 0 | 0 | 0 → 0 |
| SYN-ORIGIN | 0 | 20 | 0 | 0 | 20 → 0 |
| PUB-CN-ORIGIN | 0 | 0 | 0 | 0 | 0 → 0 |
| PUB-WCO-HS | 0 | 0 | 0 | 0 | 0 → 0 |
| PUB-US-INVOICE | 0 | 12 | 0 | 12 | not adjudicated |
| PUB-CN-DUALUSE | 0 | 0 | 0 | 0 | 0 → 0 |
| PUB-CN-DECLARATION | 0 | 14 | 0 | 13 | not adjudicated |

Before/after on the SAME saved inputs, output filter only:

| Version | Hit | Extra | Miss |
|---|---:|---:|---:|
| Raw, scope excluded | 12 | 81 | 0 |
| Offline filtered replay | 12 | 25 | 0 |

**No new misses: 0 → 0; all 12 expected anomaly pairs survive.** Every deterministic
finding is retained unchanged, including the scope note. Genuine synthetic
precondition FPs: **55 → 0**. Remaining 25 extras are public advisory citations,
not asserted to be proven FPs or silently removed to manufacture perfect metrics.

## Genuine FP sample IDs and root causes

- **SYN-AMOUNT** (16): 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 18, 19, 20.
- **SYN-HS** (2): 9, 11.
- **SYN-ORIGIN** (20): 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20.
- **SYN-REQUIRED** (17): 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17, 18, 19, 20.

- SYN-REQUIRED: model missing-field claims despite the commercial_invoice required
  precondition being false. Relevant keys: invoice_no, total_amount, currency,
  hs_code, origin_country. This is a model-output grounding error, not a fired rule.
- SYN-HS: model format claims with false actual hs_code format predicate (samples
  9 and 11). The separate missing-field condition does not establish invalid HS.
- SYN-AMOUNT: model arithmetic claims despite false total_amount/quantity/unit_price
  mismatch predicate. Existing finite/nonnegative/parse/tolerance semantics reused.
- SYN-ORIGIN: model inconsistency claims on single-document samples, where more than
  one origin_country is impossible. All 20 actual flags are false.
- SYN-RESTRICTED: **0** observed FPs; condition and regression tests still cover
  restricted markers in goods_description. No fabricated restricted FP count.
- Deterministic FPs: **0**. Field mismatches (invoice_no 5, goods_description 14,
  consignee 4) caused no extra deterministic pair here; no rule or label fix was
  justified. Labels stay unchanged.
- PUB-CN-DECLARATION 14 → 13: sample **14** had a mixed model finding citing this
  public rule and an unsupported SYN-REQUIRED claim; the whole unfounded finding
  was dropped. This does NOT adjudicate the public rule itself as a genuine FP.
  PUB-US-INVOICE remains 12. Public applicability/advisory truth needs separate
  domain review; the filter intentionally does not guess legal preconditions.

## Deterministic bounded fix (production review-output layer)

`model_findings.py` uses fired deterministic rule IDs as the single source of
precondition truth. No hard-coded sample IDs/labels and no new inference:

1. SYN-REQUIRED needs missing required fields; SYN-HS needs invalid format;
   SYN-AMOUNT needs arithmetic/format failure; SYN-RESTRICTED needs its marker;
   SYN-ORIGIN needs multiple distinct origins. False OR absent flags reject the
   model finding if ANY cited synthetic condition is unsupported.
2. Never remove or alter a deterministic finding. Remove already-covered rule
   citations from model findings; drop empty duplicates. Retain unrelated public
   guidance. Multi-citation unfounded findings are dropped as whole claims.
3. If unsupported model findings were removed, replace the model narrative summary
   with a fixed manual-review notice, avoiding republishing an ungrounded narrative.
   Record count-only filter stats in report security metadata. No response prose
   is logged. Existing provider/provenance/security checks remain enabled.

Replay filtered **56 unsupported finding objects**, deduped **6 model finding
objects**. Object counts differ from unique extra-pair counts: 55 proven synthetic
FP pairs disappear plus 1 mixed public citation. Twelve expected pairs remain.
No prompt change was made. **Prompt changes cannot be validated offline**; only
this output filter (and fixed summary-replacement branch by unit test) was validated.
This is a small synthetic benchmark, not a claim of universal legal recall or
per-document semantic equivalence for all future multi-document model prose.

## Offline reproducibility / safeguards

From backend, without model credentials:
```sh
python -m eval.replay_model_fp \
  --capture ../reports/evidence/backend-eval-model-fp/live \
  --output ../reports/evidence/backend-eval-model-fp/replay.json
```
Replay issues no HTTP/model requests; metadata and boolean predicates are enough.
Per-sample replay rejects any newly introduced miss and any removed deterministic
finding. Regression pins the real captured 12/81/0 → 12/25/0 result. Unit cases
cover every predicate, origin multiplicity, amount tolerance/invalid values,
missing-condition fail-closed behavior, mixed citations, dedupe, actual-vs-ledger
filter equivalence, all 20 GOLD cases with adversarial model findings, and the
40-request budget using mock HTTP only. Fake tests are not inference evidence.

## Validation / scans / incremental delivery

Offline targeted tests: **18 passed**. Full regression with live isolated DB/Redis,
all model opt-ins and cloud keys removed from child env: **418 passed / 6 skipped
in 103.40s**. The first regression caught one legacy fake-pipeline assertion that
required a duplicate model finding. It now asserts the single fixture finding is
filtered, all rule findings remain, and the successful reasoning trace remains;
the complete final suite passes. No paid regression test ran.

Ruff passed; Bandit over backend/app and backend/eval passed. Gitleaks full worktree
and final commit range passed with 0 leaks. Actual private-key byte comparison
is performed in-process and emits **0 hits** only. Original balances were never
serialized; private runtime configuration and injector scripts are not committed.

Portable ledgers/replay/accounting/regression/scans: reports/evidence/backend-eval-model-fp/.
Machine evidence with README and SHA256SUMS: /workspace/competition/backend-model-fp-evidence/.

No push; one incremental bundle requiring fa06661:
```sh
git bundle create /workspace/competition/bundles/feat-backend-eval-model-fp.bundle fa06661..feat/backend-eval-model-fp
git bundle verify /workspace/competition/bundles/feat-backend-eval-model-fp.bundle
sha256sum /workspace/competition/bundles/feat-backend-eval-model-fp.bundle
```
The coordinator may restart 8002 after merge; this task did not restart it.
