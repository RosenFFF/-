# Value-free restart / summary / prompt evidence

See ../../progress/backend-review-summary-prompt.md for definitions, counts and limitations.
- restart-c8c9a00: byte-identical archived snapshot of the new loopback harness proofs/scripts. Original environment-proof.json is mode600; Git cannot preserve 600 on checkout. No private values included. No restart or smoke script should be re-executed automatically.
- previous-summary-audit.json: historical 20 records have no summary prose; kept/rebuilt unknown20, no invented text and no model calls.
- live-five/: one actual DeepSeek run, IDs1/9/12/15/18; atomic provenance ledgers, no document text or values. summary_rebuilt is a live recorded decision, not saved summary text.
- five-comparison.json: offline replay of current five and exactly the same historical IDs; actual returned post-filter metadata checked against replay. Scope excluded; remaining public guidance extras unadjudicated.
- accounting-five.json: model10, chat0, balanceGET2; only difference CNY0.00, never actual balance. Difference does not establish final/free billing.
- paid-five-pytest.txt / regression.txt / scans.json: redacted receipts (portable text copies strip trailing whitespace; external originals retained). All paid opt-ins disabled in full regression.

SHA256SUMS excludes itself; nested restart-c8c9a00/SHA256SUMS is the original harness inventory. Runtime server logs are intentionally not portable evidence. Running API is pinned c8c9a00, not the feature branch.
