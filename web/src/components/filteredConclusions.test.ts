import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import en from "../i18n/en.json";
import vi from "../i18n/vi.json";
import zh from "../i18n/zh.json";
import { unsupportedFindingCount } from "../api/modelOutputFilter";
import { FilteredConclusions } from "./FilteredConclusions";

function markup(security: unknown) {
  return renderToStaticMarkup(h(FilteredConclusions, { security }));
}

const filter = (unsupported: unknown, extra: Record<string, unknown> = {}) => ({
  model_output_filter: { unsupported_finding: unsupported, ...extra },
});

afterEach(async () => {
  await i18n.changeLanguage("zh");
});

describe("filtered conclusions line", () => {
  it.each([
    ["zh", "已过滤 2 条无依据的模型结论"],
    ["en", "Filtered 2 ungrounded model conclusions"],
    ["vi", "Đã lọc 2 kết luận mô hình không có căn cứ"],
  ])("%s renders the dropped count only", async (lang, sentence) => {
    await i18n.changeLanguage(lang);
    const html = markup(filter(2, { duplicate_finding: 9, duplicate_citations_removed: 4 }));
    expect(html).toContain(sentence);
    expect(html).toContain('data-count="2"');
    expect(html).not.toContain("9");
    expect(html).not.toContain("4");
    expect(html).not.toContain("degrade-strip");
    expect(html).not.toContain("tabindex");
    expect(html).not.toContain('role="status"');
  });

  it("hides both semantic zero and a missing filter dictionary", () => {
    const presentZero = { model_output_filter: {} };
    const duplicateOnly = { model_output_filter: { duplicate_finding: 5, duplicate_citations_removed: 2 } };
    const missing = {};
    expect(unsupportedFindingCount(presentZero)).toEqual({ kind: "zero" });
    expect(unsupportedFindingCount(duplicateOnly)).toEqual({ kind: "zero" });
    expect(unsupportedFindingCount(missing)).toEqual({ kind: "absent" });
    expect(unsupportedFindingCount({ model_output_filter: null })).toEqual({ kind: "null" });
    expect(unsupportedFindingCount({ model_output_filter: [] })).toEqual({ kind: "invalid" });
    for (const security of [presentZero, duplicateOnly, missing, { model_output_filter: null }, { model_output_filter: [] }]) {
      expect(markup(security), JSON.stringify(security)).toBe("");
    }
  });

  it("hides zero and every non-count payload", () => {
    const hidden = [
      filter(0),
      filter(-0),
      undefined,
      null,
      {},
      { model_output_filter: null },
      { model_output_filter: {} },
      filter(null),
      filter(-2),
      filter(1.5),
      filter("3"),
      filter("0"),
      filter(Number.NaN),
      filter(Number.POSITIVE_INFINITY),
      filter(Number.NEGATIVE_INFINITY),
      filter(true),
      { model_output_filter: [] },
      { model_output_filter: { duplicate_finding: 5 } },
      { invalid_citations_dropped: 5, output_checks_passed: false },
      { flags: { model_output_filter: { unsupported_finding: 5 } } },
    ];
    for (const security of hidden) {
      expect(markup(security), JSON.stringify(security)).toBe("");
    }
  });

  it("does not describe the remaining findings as legally validated", () => {
    const texts = [zh, en, vi].map((table) => table["report.filteredUngrounded"]);
    expect(texts[0]).toBe("已过滤 {{count}} 条无依据的模型结论");
    for (const text of texts) {
      expect(text).not.toMatch(/合规已通过|已验证合法|legally validated|compliance passed|đã đạt tuân thủ/i);
    }
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
    expect(Object.keys(zh).sort()).toEqual(Object.keys(vi).sort());
  });
});
