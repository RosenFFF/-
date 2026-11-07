import { describe, expect, it } from "vitest";
import { unsupportedFindingCount } from "./modelOutputFilter";

const security = (unsupported: unknown, extra: Record<string, unknown> = {}) => ({
  model_output_filter: { unsupported_finding: unsupported, ...extra },
  invalid_citations_dropped: 8,
  output_checks_passed: true,
});

describe("unsupported_finding is the only dropped-ungrounded count", () => {
  it("reads a positive safe integer and ignores the other counters", () => {
    expect(
      unsupportedFindingCount(
        security(3, { duplicate_finding: 9, duplicate_citations_removed: 4 }),
      ),
    ).toEqual({ kind: "count", count: 3 });
    expect(unsupportedFindingCount(security(Number.MAX_SAFE_INTEGER))).toEqual({
      kind: "count",
      count: Number.MAX_SAFE_INTEGER,
    });
  });

  it("treats a present dict that omits unsupported_finding as zero", () => {
    expect(unsupportedFindingCount(security(0))).toEqual({ kind: "zero" });
    expect(unsupportedFindingCount(security(-0))).toEqual({ kind: "zero" });
    expect(unsupportedFindingCount({ model_output_filter: {} })).toEqual({ kind: "zero" });
    expect(
      unsupportedFindingCount({
        model_output_filter: { duplicate_finding: 5, duplicate_citations_removed: 2 },
      }),
    ).toEqual({ kind: "zero" });
  });

  it("does not infer zero when the filter dictionary is missing", () => {
    expect(unsupportedFindingCount({})).toEqual({ kind: "absent" });
    expect(unsupportedFindingCount(undefined)).toEqual({ kind: "absent" });
    expect(unsupportedFindingCount({ invalid_citations_dropped: 7 })).toEqual({ kind: "absent" });
    expect(
      unsupportedFindingCount({
        flags: { model_output_filter: { unsupported_finding: 6 } },
      }),
    ).toEqual({ kind: "absent" });
  });

  it("does not coerce null, strings, fractions, nonfinite, or malformed values", () => {
    expect(unsupportedFindingCount(null)).toEqual({ kind: "null" });
    expect(unsupportedFindingCount({ model_output_filter: null })).toEqual({ kind: "null" });
    expect(unsupportedFindingCount(security(null))).toEqual({ kind: "null" });
    for (const value of [-1, -3, 1.5, 0.1, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, "2", "0", " 3 ", true, false, [], { n: 1 }]) {
      expect(unsupportedFindingCount(security(value)), String(value)).toEqual({ kind: "invalid" });
    }
    expect(unsupportedFindingCount("security")).toEqual({ kind: "invalid" });
    expect(unsupportedFindingCount([])).toEqual({ kind: "invalid" });
    expect(unsupportedFindingCount({ model_output_filter: [] })).toEqual({ kind: "invalid" });
    expect(unsupportedFindingCount({ model_output_filter: 4 })).toEqual({ kind: "invalid" });
  });

  it("does not turn a malformed dictionary or a bad unsupported value into zero", () => {
    expect(unsupportedFindingCount({ model_output_filter: [] })).toEqual({ kind: "invalid" });
    expect(unsupportedFindingCount({ model_output_filter: 4 })).toEqual({ kind: "invalid" });
    expect(unsupportedFindingCount(security("2"))).toEqual({ kind: "invalid" });
    expect(
      unsupportedFindingCount({
        model_output_filter: { unsupported_finding: "0", duplicate_finding: 5 },
      }),
    ).toEqual({ kind: "invalid" });
    expect(unsupportedFindingCount(security(3, { duplicate_finding: 9 }))).toEqual({
      kind: "count",
      count: 3,
    });
  });
});
