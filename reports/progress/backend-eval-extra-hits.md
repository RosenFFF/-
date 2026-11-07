# ST-143: offline attribution audit of the 89 extra cited-rule pairs

Base `40669a6`; branch `feat/backend-eval-extra-hits`. No fetch was needed: the
coordinator's merged commit was already local. **0 model calls** (DeepSeek, other
paid providers, and Ollama). No listener/service restart and no production row read.

## Recoverable result — correction is 12 hit / 89 extra / 0 miss

The historical scorer counted distinct `(synthetic sample id, cited rule id)` pairs,
not finding objects. Several findings citing one rule count once in that sample.
Original **32 hit / 89 extra / 0 miss** remains visible in the unchanged one-round
artifact. Its `false_positive` property was a misleading name: it counted all cited
rule IDs absent from labels, without checking provenance or domain correctness.

Corrected definition: remove **SYN-REVIEW** from BOTH expected and actual rule sets,
then count intersection as hit, actual-minus-expected as extra, and
expected-minus-actual as miss. Do not remove all `info` findings or all model findings.
These are synthetic anomaly-label coverage counts, not independently adjudicated
legal accuracy. An extra citation is NOT automatically a genuine false positive.

All 20 labels already included SYN-REVIEW; historical miss=0 and hit=32 establish
20/20 observed scope pairs. Therefore scope notes contribute **0 of the 89 extras**.
Removing scope changes **32/89/0 → 12/89/0**, not 12/69/0 or 12/0/0. There are 12
expected eligible anomaly pairs. Legacy upload→report P50/P95/max remains
10402/12046/12363ms; 3-sample chat first-delta/done P50/P95 remains 1219/1309ms.
These timings are reused, not new inference measurements.

## Evidence loss prevents exact historical three-way attribution

The original runner saved only aggregate finding counts and per-sample model traces,
not finding rule IDs, `determined_by`, mismatch sample IDs, field values, report IDs,
or a schema-to-run mapping. Its successful PG fixture finalizer executed
`DROP SCHEMA ... CASCADE`. The saved original result and pytest output contain no
per-finding ledger. The original run's temporary directory is no longer retained.

A read-only PG catalog check found 1 surviving disposable schema, with metadata
estimates of 1 document / 1 review, not the original 20-document run. No application
rows from this unrelated schema were read, no RLS bypass or role switching was
attempted, and no encrypted files/credentials were searched for decryption.
The surviving later local-test temporary directory is not the original paid run.

Thus **all 89 original extras remain unattributed by rule ID/source**. Exact
model-generated versus deterministic-extra counts, actual FP sample IDs, and
per-case root causes are unavailable, not zero. Replaying the rule engine on GOLD
labels cannot reconstruct the original extracted fields or the model findings.
No paid rerun, local-model substitution, or hypothetical reconstruction is used.

### Bucket table: exact observations versus explicit unknowns

Counts use unique sample/rule pairs. `unknown` must not be summed as zero. The
scope column is excluded scope pairs, not extras. Genuine-FP column means an extra
emitted by the deterministic rule engine under these synthetic labels, not a claim
that model extras are factually correct.

| Rule ID | Fixed scope pairs | Model-only extra pairs | Deterministic extra / genuine FP pairs |
|---|---:|---:|---:|
| SYN-REVIEW | 20 (0 extras) | 0 eligible | 0 eligible |
| SYN-REQUIRED | 0 | unknown | unknown; upper bound 5 |
| SYN-HS | 0 | unknown | 0 (input-score proof) |
| SYN-AMOUNT | 0 | unknown | 0 (input-score proof) |
| SYN-RESTRICTED | 0 | unknown | unknown; upper bound 14 |
| SYN-ORIGIN | 0 | unknown | 0 (one document per sample) |
| PUB-CN-ORIGIN | 0 | unknown | 0 (not emitted by deterministic engine) |
| PUB-WCO-HS | 0 | unknown | 0 (not emitted by deterministic engine) |
| PUB-US-INVOICE | 0 | unknown | 0 (not emitted by deterministic engine) |
| PUB-CN-DUALUSE | 0 | unknown | 0 (not emitted by deterministic engine) |
| PUB-CN-DECLARATION | 0 | unknown | 0 (not emitted by deterministic engine) |

Total historical extras: scope **0**, model-only **unknown**, deterministic
**unknown**, unresolved **89**. The latter is an evidence-gap status, not a fourth
semantic category or a fabricated allocation.

### Bounds (not observed bucket counts)

The original field exact-match totals are 20/20 for total_amount, currency,
hs_code, origin_country, quantity, unit_price; invoice_no is 15/20 and
goods_description is 6/20. Review snapshots were created immediately from those
same fields, with no edits, and every sample has one commercial invoice.
Under those recorded input invariants, SYN-HS / SYN-AMOUNT cannot introduce
unexpected deterministic hits; SYN-ORIGIN cannot fire. Only the 5 invoice_no
mismatches could introduce extra SYN-REQUIRED, and only the 14 goods_description
mismatches could introduce extra SYN-RESTRICTED. Each rule counts at most once per
sample. Therefore deterministic extras are **0..19**, model-only extras **70..89**.
These bounds do NOT identify a rule's observed count or any actual FP sample ID.
A sample/rule emitted by both producers is assigned to deterministic-extra for
exclusive accounting, preserving both producers in the ledger.

## Root-cause limits and concrete fixes/plans

| Rule / issue | What is established | Actual FP sample IDs | Fix or plan |
|---|---|---|---|
| SYN-REVIEW metric | Universal scope inflated hit denominator by 20; caused 0 extras | none | Implemented scope-ID exclusion on both sides, while retaining legacy counts |
| SYN-REQUIRED | Possible extra requires absent invoice_no among 5 mismatches; other required input scores are exact | unknown, not inferred from sample order | Preserve rule field_keys + per-sample mismatch keys; if an extra is confirmed, audit OCR/extraction grounding for invoice_no rather than weaken REQUIRED |
| SYN-RESTRICTED | Possible extra requires an erroneous goods_description; actual presence/count unknown | unknown | Preserve metadata; if confirmed, distinguish OCR versus model grounding before designing a restricted-marker/manual-review policy; no unproven rule suppression |
| SYN-HS / SYN-AMOUNT / SYN-ORIGIN | Deterministic extra count is 0 under the recorded input/single-document invariants | none for deterministic extras | No rule change warranted |
| PUB-* and model-produced SYN-* | Model-only extras may be general guidance outside anomaly labels; exact counts/content lost | unknown | Preserve provenance; adjudicate against the synthetic task/jurisdiction before calling an extra a domain FP; do not automatically discard all model/info findings |
| Evidence retention | Aggregation plus fixture cleanup lost required attribution data | all 20 original sample ledgers absent | Implemented compact per-sample finding ledger and field_mismatch_keys, saved before schema teardown on any future authorized eval; no new run executed |

Offline deterministic rule checks on GOLD labels: **20/20 label sets agree**.
This validates the synthetic label/rule contract, NOT the original extraction or
historical FP count. No label error was demonstrated; no labels changed. No
production rule or security policy was changed without supporting evidence.

## Implementation / reproducibility

- `eval/finding_metrics.py`: deduplicated scope-aware scoring, exclusive source
  attribution, and offline ledger aggregation; rejects unknown provenance and
  duplicate sample IDs. Stored metadata omits prose, document IDs and field values.
- Opt-in evaluator now persists `finding_metadata`, expected rule IDs,
  `field_mismatch_keys`, per-sample score and aggregate corrected counts. Legacy
  `finding_counts` remains unchanged for traceability. This is instrumentation,
  not retrospective evidence and not permission for another model run.
- `eval/audit_extra_hits.py`: offline correction/bounds plus GOLD-label oracle;
  explicitly emits null counts for unavailable historical provenance.

Command from backend, without model credentials:
```sh
/workspace/competition/live-deepseek-71311f4-src/backend/.venv/bin/python -m eval.audit_extra_hits \
  --input ../reports/evidence/backend-eval-ollama/deepseek-one-round.json \
  --output ../reports/evidence/backend-eval-extra-hits/audit.json
```

## Tests / scans / delivery

Offline targeted tests: **6 passed in 0.02s**. GOLD-label oracle **20/20**.
Full regression with isolated live PostgreSQL/Redis fixtures: **406 passed,
5 skipped in 116.64s**. All RUN_* flags and cloud model keys were removed from the
regression child environment; no opt-in model test ran. Ruff passed. Bandit over
`backend/app` AND `backend/eval` passed; worktree and final commit-range gitleaks
passed with 0 leaks; actual private-key byte comparison emitted **0 hits** only.
Credentials stayed in child environments; no runtime JSON, secrets or field values
were committed. The original one-round evidence was not altered.

Machine-local checks/scan logs: `/workspace/competition/backend-extra-hits-evidence/`.
Selected value-free audit, recovery summary and regression/scan summary are bundled
under `reports/evidence/backend-eval-extra-hits/`, with SHA256SUMS.

Incremental delivery commands (no push, base already local):
```sh
git bundle create /workspace/competition/bundles/feat-backend-eval-extra-hits.bundle 40669a6..feat/backend-eval-extra-hits
git bundle verify /workspace/competition/bundles/feat-backend-eval-extra-hits.bundle
sha256sum /workspace/competition/bundles/feat-backend-eval-extra-hits.bundle
```
The bundle requires base commit `40669a6`. Exact historical bucket counts/sample
IDs remain an explicit **unfulfilled evidence-dependent part** of the request;
measurement fixes and mathematically identifiable counts are complete. No result
has been invented to present an unavailable attribution as successful.
