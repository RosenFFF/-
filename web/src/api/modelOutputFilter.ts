/**
 * Review response path, from c8c9a00 review_out:
 * security.model_output_filter.unsupported_finding
 *
 * filter_model_findings stores only keys whose count is greater than zero.
 * A real dictionary without unsupported_finding therefore means zero dropped
 * ungrounded conclusions. A missing dictionary means the filter did not run.
 * duplicate_finding and duplicate_citations_removed are never read.
 */

export type FilterCount =
  | { kind: "absent" }
  | { kind: "null" }
  | { kind: "invalid" }
  | { kind: "zero" }
  | { kind: "count"; count: number };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function unsupportedFindingCount(security: unknown): FilterCount {
  if (security === undefined) return { kind: "absent" };
  if (security === null) return { kind: "null" };
  if (!isRecord(security) || !Object.prototype.hasOwnProperty.call(security, "model_output_filter")) {
    return isRecord(security) ? { kind: "absent" } : { kind: "invalid" };
  }
  const filter = security.model_output_filter;
  if (filter === undefined) return { kind: "absent" };
  if (filter === null) return { kind: "null" };
  if (!isRecord(filter)) return { kind: "invalid" };
  // Backend omits zero counts. A present dict without this key is zero, not "unknown".
  if (!Object.prototype.hasOwnProperty.call(filter, "unsupported_finding")) {
    return { kind: "zero" };
  }
  const value = filter.unsupported_finding;
  if (value === null) return { kind: "null" };
  if (typeof value !== "number" || !Number.isFinite(value) || !Number.isSafeInteger(value) || value < 0) {
    return { kind: "invalid" };
  }
  if (value === 0) return { kind: "zero" };
  return { kind: "count", count: value };
}
