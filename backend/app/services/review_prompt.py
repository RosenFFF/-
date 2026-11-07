"""Versioned, explicit synthetic trigger semantics; not a real-law rule expansion."""

SYNTHETIC_REVIEW_PRECONDITIONS = """
Synthetic-rule preconditions (emit a concrete finding ONLY when its condition holds):
- SYN-REQUIRED: at least one required field for that document type is absent/empty.
  For commercial_invoice the required keys are invoice_no, total_amount, currency,
  hs_code, origin_country. Optional consignee, quantity, certificate_no, etc. are NOT
  missing-required violations for an invoice. A general verification reminder is not a violation.
- SYN-HS: an actually supplied hs_code fails the format of exactly 6, 8 or 10 digits.
  A missing hs_code is a required-field issue, NOT an invalid-format issue.
- SYN-AMOUNT: total_amount, quantity and unit_price must ALL be present. Emit only
  if numeric parsing/finite/nonnegative validation fails, or abs(total_amount -
  quantity * unit_price) > 0.01. Matching arithmetic is NOT a mismatch finding.
- SYN-RESTRICTED: goods_description contains DEMO-RESTRICTED or SYNTHETIC-EMBARGO
  (case-insensitive). A general sanctions-check suggestion is NOT a marker hit.
- SYN-ORIGIN: ONLY when >1 distinct non-empty origin_country occurs across documents
  of the SAME review. Single-document reviews MUST NEVER cite SYN-ORIGIN. A missing
  origin or missing origin certificate alone is NOT cross-document inconsistency.
- SYN-REVIEW: scope/manual-review note only, NOT an anomaly.
Do NOT cite an untriggered synthetic rule for generic advice. Separate unverified
public-source guidance from actual document defects; never assert legal clearance.
""".strip()
