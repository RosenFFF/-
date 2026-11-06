import { createElement as h, Fragment } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import {
  CitationSource,
  ReportRuleSource,
  ReportVerification,
} from "../components/Provenance";
import { sourceKind, sourceUrl, verificationKey } from "./provenance";
import type { Review, SourceMetadata } from "./types";

const review: Review = {
  id: "fixture",
  status: "completed",
  created_at: "2026-11-05",
  language: "zh-CN",
  destination_country: "RU",
  findings: [],
  degrade_level: "L3",
};
const citation: SourceMetadata = {
  source_kind: "public",
  url: "https://example.org/development-only/summary",
  article: "MOCK § 3.2",
  version_date: "2026-11-05",
};
afterEach(async () => {
  await i18n.changeLanguage("zh");
});
describe("separate report verification and citation provenance", () => {
  it.each([
    [
      "zh",
      "规则引擎回退，未完成真实 LLM 验证",
      "合成规则 · 非真实合规结论",
      "公开摘要，非法规原文，不代表已通过合规验证",
      "来源信息缺失",
    ],
    [
      "en",
      "Rule-engine fallback; real LLM validation has not been completed",
      "Synthetic rules · Not a real compliance conclusion",
      "Public summary, not the original regulation; this does not mean compliance validation has passed",
      "Source information missing",
    ],
    [
      "vi",
      "Dự phòng bằng bộ quy tắc, chưa hoàn tất xác minh bằng LLM thực",
      "Quy tắc tổng hợp · Không phải kết luận tuân thủ thực tế",
      "Tóm tắt công khai, không phải nguyên văn quy định; không có nghĩa là đã vượt qua xác minh tuân thủ",
      "Thiếu thông tin nguồn",
    ],
  ])(
    "%s provides explicit, independent warnings",
    async (lang, fallback, synthetic, disclaimer, missing) => {
      await i18n.changeLanguage(lang);
      const status = renderToStaticMarkup(
        h(ReportVerification, { report: review }),
      );
      const publicCitation = renderToStaticMarkup(
        h(CitationSource, { value: citation }),
      );
      const syntheticCitation = renderToStaticMarkup(
        h(CitationSource, { value: { source_kind: "synthetic" } }),
      );
      const absent = renderToStaticMarkup(h(CitationSource, { value: {} }));
      expect(status).toContain(fallback);
      expect(status).not.toContain(synthetic);
      expect(publicCitation).toContain(disclaimer);
      expect(publicCitation).not.toContain(synthetic);
      expect(syntheticCitation).toContain(synthetic);
      expect(syntheticCitation).not.toContain(disclaimer);
      expect(absent).toContain(missing);
      expect(absent).not.toContain(synthetic);
    },
  );
  it("renders every explicit metadata field, without guessing effective/version dates", () => {
    const html = renderToStaticMarkup(h(CitationSource, { value: citation }));
    for (const text of [citation.url, citation.article, citation.version_date])
      expect(html).toContain(text);
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).not.toContain("来源信息缺失");
  });
  it.each(["L0", "L1", "L2"] as const)(
    "%s does not claim rule-engine fallback",
    (level) => {
      const html = renderToStaticMarkup(
        h(ReportVerification, { report: { ...review, degrade_level: level } }),
      );
      expect(html).not.toContain("规则引擎回退");
      expect(html).toContain("人工复核");
    },
  );
  it("an explicit false validation flag is not overridden by L0", () => {
    expect(verificationKey({ degrade_level: "L0", llm_verified: false })).toBe(
      "report.verification.unverified",
    );
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
    expect(html).toContain("规则引擎回退，未完成真实 LLM 验证");
    expect(html).toContain('data-source-kind="public"');
    expect(html).not.toContain("合成规则");
  });
  it("missing report provenance is not inferred from its L3 status", () => {
    const html = renderToStaticMarkup(h(ReportRuleSource, { report: review }));
    expect(html).toContain("来源信息缺失");
    expect(html).not.toContain("合成规则");
  });
  it("uses explicit aggregate source and retrieval flags only", () => {
    const html = renderToStaticMarkup(
      h(ReportRuleSource, {
        report: {
          ...review,
          security: {
            source_kind: "synthetic",
            retrieval_mode: "lightweight_hash",
            compliance_disclaimer: "SERVER DISCLAIMER",
          },
        },
      }),
    );
    expect(html).toContain("合成规则 · 非真实合规结论");
    expect(html).toContain("非 BGE");
    expect(html).toContain("SERVER DISCLAIMER");
    expect(html).toContain("<section");
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
          url: null,
          article: "  ",
          version_date: null,
        },
      }),
    );
    expect(html.match(/来源信息缺失/g)).toHaveLength(4);
    expect(html).not.toContain("href=");
  });
});
