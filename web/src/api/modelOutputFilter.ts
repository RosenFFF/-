/**
 * Review response path, from c8c9a00 review_out:
 * security.model_output_filter.unsupported_finding
 *
 * filter_model_findings increments unsupported_finding once per model finding
 * dropped because a cited synthetic precondition was not true.
 * duplicate_finding and duplicate_citations_removed are different counters and
 * are never read. Other security fields are not this count.
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
  if (!isRecord(filter) || !Object.prototype.hasOwnProperty.call(filter, "unsupported_finding")) {
    return isRecord(filter) ? { kind: "absent" } : { kind: "invalid" };
  }
  const value = filter.unsupported_finding;
  if (value === undefined) return { kind: "absent" };
  if (value === null) return { kind: "null" };
  if (typeof value !== "number" || !Number.isFinite(value) || !Number.isSafeInteger(value) || value < 0) {
    return { kind: "invalid" };
  }
  if (value === 0) return { kind: "zero" };
  return { kind: "count", count: value };
}
