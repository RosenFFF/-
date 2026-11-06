import { createElement as h, Fragment } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import {
  CitationSource,
  ReportRuleSource,
  ReportVerification,
} from "../components/Provenance";
import {
  degradeStatusText,
  sourceKind,
  sourceUrl,
} from "./provenance";
import type { Review, SourceMetadata } from "./types";

const L3_STATUS = "规则引擎回退，未完成真实 LLM 验证";
const review: Review = {
  id: "fixture",
  status: "completed",
  created_at: "2026-11-05",
  language: "zh-CN",
  destination_country: "RU",
  findings: [],
  degrade_level: "L3",
  degrade_status: L3_STATUS,
  llm_verified: false,
};
const citation: SourceMetadata = {
  source_kind: "public",
  source_kind_label: "公开出处已核验 · 仍须人工复核",
  url: "https://example.org/development-only/summary",
  article: "MOCK § 3.2",
  version_date: "2026-11-05",
  excerpt_kind: "summary",
  applicability: "unverified",
};
afterEach(async () => {
  await i18n.changeLanguage("zh");
});
describe("wire degrade_status and citation provenance", () => {
  it("renders degrade_status from the response, never fixed frontend L-level copy", () => {
    const html = renderToStaticMarkup(
      h(ReportVerification, { report: review }),
    );
    expect(html).toContain(L3_STATUS);
    expect(html).toContain("未完成");
    expect(html).toContain("L3");
    // Must not invent alternate L3 phrasing when the wire field is present.
    expect(html).not.toContain("状态信息缺失");
  });
  it.each([
    ["zh", "状态信息缺失", "未完成"],
    ["en", "Status information missing", "Not completed"],
    ["vi", "Thiếu thông tin trạng thái", "Chưa hoàn tất"],
  ])(
    "%s shows missing status copy only when degrade_status is absent",
    async (lang, missing, unverified) => {
      await i18n.changeLanguage(lang);
      const absent = renderToStaticMarkup(
        h(ReportVerification, {
          report: { degrade_level: "L3", llm_verified: false },
        }),
      );
      expect(absent).toContain(missing);
      expect(absent).toContain(unverified);
      expect(absent).not.toContain(L3_STATUS);
      const present = renderToStaticMarkup(
        h(ReportVerification, { report: review }),
      );
      expect(present).toContain(L3_STATUS);
      expect(present).not.toContain(missing);
    },
  );
  it("does not substitute frontend fixed text for other degrade levels", () => {
    for (const level of ["L0", "L1", "L2"] as const) {
      const status = `SERVER STATUS ${level}`;
      const html = renderToStaticMarkup(
        h(ReportVerification, {
          report: {
            degrade_level: level,
            degrade_status: status,
            llm_verified: true,
          },
        }),
      );
      expect(html).toContain(status);
      expect(html).not.toContain(L3_STATUS);
      expect(html).not.toContain("状态信息缺失");
    }
  });
  it("degradeStatusText reads the wire field only", () => {
    expect(degradeStatusText(review)).toBe(L3_STATUS);
    expect(degradeStatusText({ degrade_status: "  " })).toBeNull();
    expect(degradeStatusText({})).toBeNull();
  });
  it.each([
    [
      "zh",
      "合成规则 · 非真实合规结论",
      "公开摘要，非法规原文，不代表已通过合规验证",
      "来源信息缺失",
      "适用范围未核验，不构成完整适用性证据，不代表合规已通过",
    ],
    [
      "en",
      "Synthetic rules · Not a real compliance conclusion",
      "Public summary, not the original regulation; this does not mean compliance validation has passed",
      "Source information missing",
      "Applicability unverified; not full applicability evidence and not a passed compliance result",
    ],
    [
      "vi",
      "Quy tắc tổng hợp · Không phải kết luận tuân thủ thực tế",
      "Tóm tắt công khai, không phải nguyên văn quy định; không có nghĩa là đã vượt qua xác minh tuân thủ",
      "Thiếu thông tin nguồn",
      "Khả năng áp dụng chưa được xác minh; không phải bằng chứng áp dụng đầy đủ và không phải kết quả tuân thủ đã đạt",
    ],
  ])(
    "%s keeps citation warnings independent of report status",
    async (lang, synthetic, disclaimer, missing, applicabilityNote) => {
      await i18n.changeLanguage(lang);
      const publicCitation = renderToStaticMarkup(
        h(CitationSource, { value: citation }),
      );
      const syntheticCitation = renderToStaticMarkup(
        h(CitationSource, {
          value: {
            source_kind: "synthetic",
            source_kind_label: synthetic,
            excerpt_kind: "summary",
            applicability: "unverified",
          },
        }),
      );
      const absent = renderToStaticMarkup(h(CitationSource, { value: {} }));
      expect(publicCitation).toContain(disclaimer);
      expect(publicCitation).toContain(applicabilityNote);
      expect(publicCitation).toContain(citation.source_kind_label!);
      expect(publicCitation).not.toContain(synthetic);
      expect(syntheticCitation).toContain(synthetic);
      expect(syntheticCitation).toContain(disclaimer);
      expect(absent).toContain(missing);
      expect(absent).not.toContain(synthetic);
    },
  );
  it("renders every explicit metadata field, without guessing dates", () => {
    const html = renderToStaticMarkup(h(CitationSource, { value: citation }));
    for (const text of [
      citation.url,
      citation.article,
      citation.version_date,
      citation.source_kind_label,
    ])
      expect(html).toContain(text);
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("摘要");
    expect(html).not.toContain("来源信息缺失");
  });
  it("a public citation stays public during L3 fallback", () => {
    const html = renderToStaticMarkup(
      h(
        Fragment,
        null,
        h(ReportVerification, { report: review }),
        h(CitationSource, { value: citation }),
      ),
    );
    expect(html).toContain(L3_STATUS);
    expect(html).toContain('data-source-kind="public"');
    expect(html).not.toContain("合成规则");
  });
  it("missing report provenance is not inferred from its L3 status", () => {
    const html = renderToStaticMarkup(h(ReportRuleSource, { report: review }));
    expect(html).toContain("来源信息缺失");
    expect(html).not.toContain("合成规则");
  });
  it("uses explicit aggregate source labels only", () => {
    const html = renderToStaticMarkup(
      h(ReportRuleSource, {
        report: {
          ...review,
          security: {
            source_kind: "synthetic",
            source_kind_label: "合成规则 · 非真实合规结论",
            rule_corpus_label: "合成或未核验语料（非真实合规结论）",
            retrieval_mode: "lightweight_hash",
            compliance_disclaimer: "SERVER DISCLAIMER",
          },
        },
      }),
    );
    expect(html).toContain("合成规则 · 非真实合规结论");
    expect(html).toContain("合成或未核验语料");
    expect(html).toContain("非 BGE");
    expect(html).toContain("SERVER DISCLAIMER");
  });
  it("does not invent source_kind_label from source_kind alone", () => {
    const html = renderToStaticMarkup(
      h(CitationSource, { value: { source_kind: "synthetic" } }),
    );
    expect(html).toContain("来源信息缺失");
    expect(html).not.toContain("合成规则 · 非真实合规结论");
  });
  it.each([
    undefined,
    null,
    "",
    "SYNTHETIC",
    "public_verified",
    "synthetic mentioned in summary",
  ])("unknown kind %j is missing, never inferred", (kind) => {
    expect(sourceKind(kind)).toBeNull();
  });
  it.each(["synthetic", "public"] as const)(
    "accepts explicit %s only",
    (kind) => expect(sourceKind(kind)).toBe(kind),
  );
  it.each([
    null,
    undefined,
    "",
    "javascript:alert(1)",
    "data:text/html,fixture",
    "/relative",
    "//example.org",
    "file:///tmp/fixture",
  ])("rejects unsafe/missing source URL %j", (url) => {
    expect(sourceUrl(url)).toBeNull();
    expect(
      renderToStaticMarkup(h(CitationSource, { value: { ...citation, url } })),
    ).not.toContain("href=");
  });
  it("rejects credential-bearing URLs", () => {
    const url = new URL("https://example.org");
    url.username = "fixture";
    url.password = "fixture";
    expect(sourceUrl(url.href)).toBeNull();
  });
  it.each(["https://example.org/summary", "http://example.org/summary"])(
    "accepts absolute public web URL %s",
    (url) => expect(sourceUrl(url)).toBe(url),
  );
  it("synthetic missing url/date use explicit placeholders, never invented values", () => {
    const html = renderToStaticMarkup(
      h(CitationSource, {
        value: {
          source_kind: "synthetic",
          source_kind_label: "合成规则 · 非真实合规结论",
          excerpt_kind: "summary",
          applicability: "unverified",
        },
      }),
    );
    expect(html).toContain("无公开来源");
    expect(html).toContain("版本未提供");
    expect(html).not.toContain("href=");
    expect(html).not.toContain("2025-");
  });
  it("public missing url/date keep generic source-missing copy", () => {
    const html = renderToStaticMarkup(
      h(CitationSource, {
        value: {
          source_kind: "public",
          source_kind_label: "公开出处已核验 · 仍须人工复核",
          excerpt_kind: "summary",
          applicability: "unverified",
        },
      }),
    );
    expect(html).toContain("来源信息缺失");
    expect(html).not.toContain("无公开来源");
    expect(html).not.toContain("版本未提供");
  });
  it.each([
    ["zh", "无公开来源", "版本未提供"],
    ["en", "No public source", "Version not provided"],
    ["vi", "Không có nguồn công khai", "Chưa cung cấp phiên bản"],
  ])("%s translates synthetic placeholders", async (lang, noUrl, noVersion) => {
    await i18n.changeLanguage(lang);
    const html = renderToStaticMarkup(
      h(CitationSource, {
        value: {
          source_kind: "synthetic",
          source_kind_label: "合成规则 · 非真实合规结论",
        },
      }),
    );
    expect(html).toContain(noUrl);
    expect(html).toContain(noVersion);
  });
    it("does not invent version_date from other date fields", () => {
    const metadata = {
      ...citation,
      version_date: undefined,
      verified_at: "2025-01-01",
      effective_date: "2025-02-01",
    };
    const html = renderToStaticMarkup(h(CitationSource, { value: metadata }));
    expect(html).toContain("来源信息缺失");
    expect(html).not.toContain("2025-01-01");
    expect(html).not.toContain("2025-02-01");
  });
  it("empty optional metadata stays visibly missing", () => {
    const html = renderToStaticMarkup(
      h(CitationSource, {
        value: {
          source_kind: null,
          source_kind_label: null,
          url: null,
          article: "  ",
          version_date: null,
          excerpt_kind: null,
          applicability: null,
        },
      }),
    );
    expect(html.match(/来源信息缺失/g)!.length).toBeGreaterThanOrEqual(5);
    expect(html).not.toContain("href=");
  });
});
