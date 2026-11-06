import { test, expect, type Locator, type Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import type { Api } from "../src/api/types.js";

const output =
  process.env.M1_SCREENSHOT_DIR ??
  fileURLToPath(new URL("../../../screenshots/m2/", import.meta.url));
const docId = "00000000-0000-4000-8000-000000000001";
const tabbables = "a[href],button,input,select,textarea,[tabindex]";

async function startTabOrder(page: Page) {
  await page.evaluate(() => {
    document.body.tabIndex = -1;
    document.body.focus();
  });
}
async function tabTo(page: Page, target: Locator) {
  await startTabOrder(page);
  for (let i = 0; i < 100; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement)) return;
  }
  throw new Error(`Not reachable with Tab: ${await target.textContent()}`);
}
async function tabAudit(page: Page) {
  const expected = await page.locator(tabbables).evaluateAll((elements) =>
    elements.flatMap((el, index) => {
      const node = el as HTMLElement;
      const visible =
        !!node.getClientRects().length &&
        getComputedStyle(node).visibility !== "hidden";
      if (!visible || node.tabIndex < 0 || node.matches(":disabled")) return [];
      node.dataset.e2eTab = `${index}`;
      return [
        {
          id: `${index}`,
          label:
            node.getAttribute("aria-label") ||
            node.textContent?.trim().slice(0, 60) ||
            node.tagName,
        },
      ];
    }),
  );
  await startTabOrder(page);
  const observed = [];
  for (let i = 0; i < expected.length; i++) {
    await page.keyboard.press("Tab");
    observed.push(
      await page.evaluate(() => {
        const node = document.activeElement as HTMLElement;
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        const x = Math.min(
          innerWidth - 1,
          Math.max(0, rect.left + rect.width / 2),
        );
        const y = Math.min(
          innerHeight - 1,
          Math.max(0, rect.top + rect.height / 2),
        );
        const covering = document.elementFromPoint(x, y);
        const luminance = (color: string) => {
          const rgb = color
            .match(/[\d.]+/g)
            ?.slice(0, 3)
            .map(Number) ?? [0, 0, 0];
          const linear = rgb.map((v) => {
            const channel = v / 255;
            return channel <= 0.04045
              ? channel / 12.92
              : ((channel + 0.055) / 1.055) ** 2.4;
          });
          return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
        };
        let parent = node.parentElement;
        let adjacentColor = "rgb(255,255,255)";
        while (parent) {
          const color = getComputedStyle(parent).backgroundColor;
          if (color !== "rgba(0, 0, 0, 0)" && color !== "transparent") {
            adjacentColor = color;
            break;
          }
          parent = parent.parentElement;
        }
        const a = luminance(style.outlineColor),
          b = luminance(adjacentColor);
        const focusContrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        return {
          id: node.dataset.e2eTab,
          tag: node.tagName,
          focusVisible: node.matches(":focus-visible"),
          outlineWidth: style.outlineWidth,
          outlineStyle: style.outlineStyle,
          outlineColor: style.outlineColor,
          adjacentColor,
          focusContrast,
          inViewport:
            rect.top >= 0 &&
            rect.bottom <= innerHeight &&
            rect.left >= 0 &&
            rect.right <= innerWidth,
          uncovered:
            !!covering && (node === covering || node.contains(covering)),
        };
      }),
    );
  }
  await page.evaluate(() => document.body.removeAttribute("tabindex"));
  return {
    expected,
    observed,
    orderMatches:
      expected.map((v) => v.id).join(",") ===
      observed.map((v) => v.id).join(","),
    failures: observed.filter(
      (v) =>
        !v.focusVisible ||
        parseFloat(v.outlineWidth) < 2 ||
        v.outlineStyle === "none" ||
        v.focusContrast < 3 ||
        !v.inViewport ||
        !v.uncovered,
    ),
  };
}
async function overflowAudit(page: Page) {
  await page.evaluate(() => window.scrollTo(0, 0));
  return page.evaluate(() => {
    const width = innerWidth;
    const wideElements = Array.from(
      document.querySelectorAll<HTMLElement>("body *"),
    ).flatMap((el) => {
      const rect = el.getBoundingClientRect();
      if (
        !rect.width ||
        getComputedStyle(el).visibility === "hidden" ||
        (rect.right <= width + 1 && rect.left >= -1 && rect.width <= width + 1)
      )
        return [];
      let ancestor = el.parentElement;
      let scrollContainer = "";
      while (ancestor && ancestor !== document.body) {
        const style = getComputedStyle(ancestor);
        if (["auto", "scroll", "hidden", "clip"].includes(style.overflowX)) {
          scrollContainer = `${ancestor.tagName}.${ancestor.className}`;
          break;
        }
        ancestor = ancestor.parentElement;
      }
      return [
        {
          tag: el.tagName,
          className: el.className?.toString().slice(0, 100),
          text: el.textContent?.trim().slice(0, 60),
          left: rect.left,
          right: rect.right,
          width: rect.width,
          scrollContainer,
        },
      ];
    });
    return {
      viewport: width,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      horizontalOverflow:
        document.documentElement.scrollWidth > width ||
        document.body.scrollWidth > width,
      wideElements,
      uncontained: wideElements.filter((el) => !el.scrollContainer),
    };
  });
}

test("mock review journey: screenshots, axe, overflow and real keyboard operation", async ({
  page,
}, testInfo) => {
  await mkdir(output, { recursive: true });
  const size = testInfo.project.name;
  const pageErrors: string[] = [];
  const realApiRequests: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/v1/"))
      realApiRequests.push(request.url());
  });
  const reports: Record<string, unknown>[] = [];
  const operations: Record<string, boolean> = {};
  async function snapshot(name: string) {
    await expect(page.locator(".mock-banner")).toContainText(
      "MOCK 数据 · 仅开发",
    );
    const keyboard = await tabAudit(page);
    // The dev banner must remain in the viewport after keyboard scrolling too.
    await expect(page.locator(".mock-banner")).toBeInViewport();
    const overflow = await overflowAudit(page);
    const axe = await new AxeBuilder({ page }).analyze();
    await page.evaluate(() => {
      (document.activeElement as HTMLElement)?.blur();
      window.scrollTo(0, 0);
    });
    const screenshot = resolve(output, `${name}-${size}.png`);
    await page.screenshot({
      path: screenshot,
      fullPage: true,
      animations: "disabled",
    });
    const report = {
      name,
      viewport: page.viewportSize(),
      screenshot,
      overflow,
      keyboard,
      axe: {
        violations: axe.violations,
        incomplete: axe.incomplete,
        passedRules: axe.passes.length,
        engine: axe.testEngine,
      },
    };
    reports.push(report);
    await writeFile(
      resolve(output, `${name}-${size}.json`),
      JSON.stringify(report, null, 2),
    );
  }
  async function signIn(role: "reviewer" | "admin") {
    const user = page.getByLabel("账号", { exact: true });
    await tabTo(page, user);
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.type(role);
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("密码", { exact: true })).toBeFocused();
    await page.keyboard.type("mock-visual-only");
    await expect(
      page.getByRole("button", { name: "登录", exact: true }),
    ).toBeEnabled();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/cases$/);
    await expect(page.getByRole("heading", { name: "案件列表" })).toBeVisible();
    operations[`${role}LoginEnter`] = true;
  }
  await page.goto("/login");
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toBeEnabled();
  await snapshot("login");
  await signIn("reviewer");
  await snapshot("cases");
  await page.goto("/cases/new");
  await expect(page.getByRole("heading", { name: "上传单证" })).toBeVisible();
  await snapshot("upload");
  // Native upload control; the mock adapter is explicitly enabled for this test.
  await page.locator("input[type=file]").setInputFiles({
    name: "mock-visual-invoice.png",
    mimeType: "image/png",
    buffer: Buffer.from("development-only fixture"),
  });
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/cases/${docId}/extract$`));
  await expect(page.locator(".document-image img")).toBeVisible();
  const field = page.getByRole("button", { name: "HS 编码", exact: true });
  await tabTo(page, field);
  await page.keyboard.press("Enter");
  await expect(field.locator("xpath=ancestor::tr")).toHaveClass("selected");
  await expect(page.getByTestId("bbox-highlight")).toHaveCount(1);
  const highlight = page.getByTestId("bbox-highlight");
  expect(await highlight.evaluate((el) => (el as HTMLElement).style.left)).toBe(
    "12%",
  );
  await expect(field).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".preview-nav [role=status]")).toContainText(
    "1 / 2",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(output, `keyboard-field-focus-${size}.png`),
    fullPage: true,
  });
  operations.fieldEnterHighlight = true;
  await snapshot("extract");
  const packing = page.getByRole("button", { name: "装箱单金额", exact: true });
  await tabTo(page, packing);
  await page.keyboard.press("Space");
  await expect(page.getByTestId("bbox-highlight")).toHaveCount(1);
  await expect(page.locator(".preview-nav")).toContainText("2 / 2");
  operations.fieldSpaceChangesPage = true;
  const previous = page.getByRole("button", { name: "上一页", exact: true });
  await tabTo(page, previous);
  await page.keyboard.press("Enter");
  await expect(page.locator(".preview-nav")).toContainText("1 / 2");
  await expect(page.getByTestId("bbox-highlight")).toHaveCount(0);
  operations.previousPageEnter = true;
  const next = page.getByRole("button", { name: "下一页", exact: true });
  await tabTo(page, next);
  await page.keyboard.press("Space");
  await expect(page.locator(".preview-nav")).toContainText("2 / 2");
  await expect(page.getByTestId("bbox-highlight")).toHaveCount(1);
  operations.nextPageSpace = true;
  await page.goto(`/cases/${docId}/report`);
  await page.getByRole("button", { name: "发起审查", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "继续追问", exact: true }),
  ).toBeVisible();
  // Exercise the citation drawer/text before capturing, not just closed-state axe.
  await page
    .getByRole("button", { name: "MOCK 开发规则 · RULE-AMT-01" })
    .click();
  await expect(page.locator(".rule-text")).toBeVisible();
  await expect(page.locator(".report-verification")).toContainText(
    "规则引擎回退，未完成真实 LLM 验证",
  );
  await expect(page.locator(".citation-source").first()).toContainText(
    "合成规则 · 非真实合规结论",
  );
  await expect(page.locator(".citation-source").first()).toContainText(
    "无公开来源",
  );
  await expect(page.locator(".citation-source").first()).toContainText(
    "版本未提供",
  );
  await snapshot("report");
  // Explicit browser-only mock fixtures: verify PUBLIC + L3 is not relabelled synthetic.
  async function citationFixture(scenario: "public" | "missing") {
    await page.evaluate(async (mode) => {
      const path = "/src/mock/api.ts";
      const { mockApi } = (await import(/* @vite-ignore */ path)) as {
        mockApi: Api;
      };
      const state = window as unknown as { m1RestoreReview?: () => void };
      state.m1RestoreReview?.();
      const original = mockApi.review;
      state.m1RestoreReview = () => {
        mockApi.review = original;
      };
      mockApi.review = async (...args: Parameters<Api["review"]>) => {
        const report = await original(...args);
        return {
          ...report,
          // Keep wire degrade_status; only swap citation provenance for the scenario.
          security:
            mode === "public"
              ? {
                  source_kind: "public",
                  source_kind_label: "公开出处已核验 · 仍须人工复核",
                }
              : undefined,
          findings: report.findings.map((finding) => ({
            ...finding,
            citations: finding.citations.map((c) =>
              mode === "public"
                ? {
                    ...c,
                    source_kind: "public",
                    source_kind_label: "公开出处已核验 · 仍须人工复核",
                    url: "https://example.org/development-only/public-summary",
                    article: "MOCK § 3.2",
                    version_date: "2026-11-05",
                    excerpt_kind: "summary",
                    applicability: "unverified",
                  }
                : {
                    rule_id: c.rule_id,
                    source: c.source,
                    excerpt: c.excerpt,
                  },
            ),
          })),
        };
      };
    }, scenario);
    await page.getByRole("button", { name: "重试", exact: true }).click();
  }
  await citationFixture("public");
  await expect(page.locator(".source-kind")).toHaveText("公开出处已核验 · 仍须人工复核");
  await expect(page.locator(".citation-source")).toContainText(
    "公开摘要，非法规原文，不代表已通过合规验证",
  );
  await expect(page.locator(".citation-source a")).toHaveAttribute(
    "href",
    "https://example.org/development-only/public-summary",
  );
  await expect(page.locator(".citation-source")).toContainText("MOCK § 3.2");
  await expect(page.locator(".citation-source")).toContainText("2026-11-05");
  await expect(page.locator(".report-verification")).toContainText(
    "规则引擎回退，未完成真实 LLM 验证",
  );
  await expect(page.locator(".citation-source")).not.toContainText("合成规则");
  await snapshot("report-public");
  await citationFixture("missing");
  await expect(page.locator(".source-kind")).toHaveText("来源信息缺失");
  await expect(page.locator(".citation-source a")).toHaveCount(0);
  await expect(page.locator(".citation-source")).not.toContainText("合成规则");
  await expect(page.locator(".report-rule-source")).toContainText(
    "来源信息缺失",
  );
  await snapshot("report-missing-source");
  await page.evaluate(() => {
    (window as unknown as { m1RestoreReview?: () => void }).m1RestoreReview?.();
  });
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".source-kind")).toHaveText(
    "合成规则 · 非真实合规结论",
  );
  await page.getByRole("link", { name: "继续追问", exact: true }).click();
  const question = page.getByRole("textbox", {
    name: "例如：如何修改才能合规？",
  });
  await expect(question).toBeEnabled();
  await tabTo(page, question);
  await page.keyboard.type("如何核对金额？");
  await page.keyboard.press("Enter");
  await expect(page.locator(".chat-message.assistant")).toContainText(
    "MOCK · 请核对发票与装箱单金额。",
  );
  await expect(question).toBeEnabled();
  operations.questionEnter = true;
  await snapshot("ask");
  await page.goto("/audit");
  await page.getByRole("button", { name: "全局看板", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("403");
  await snapshot("audit-reviewer-403");
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await signIn("admin");
  await page.goto("/audit");
  await page.getByRole("button", { name: "全局看板", exact: true }).click();
  await expect(page.getByText("暂无记录", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "校验哈希链", exact: true }).click();
  await expect(page.locator(".banner")).toContainText("审计链完整");
  await snapshot("audit-admin");
  await page.goto("/system/models");
  await expect(page.getByRole("table")).toBeVisible();
  await snapshot("models");
  const summary = {
    viewport: page.viewportSize(),
    operations,
    pageErrors,
    realApiRequests,
    reports,
  };
  await writeFile(
    resolve(output, `summary-${size}.json`),
    JSON.stringify(summary, null, 2),
  );
  const failures = reports.flatMap((raw) => {
    const report = raw as {
      name: string;
      overflow: Awaited<ReturnType<typeof overflowAudit>>;
      keyboard: Awaited<ReturnType<typeof tabAudit>>;
      axe: { violations: { id: string }[]; incomplete: { id: string }[] };
    };
    return [
      ...(report.overflow.horizontalOverflow
        ? [`${report.name}: document overflow`]
        : []),
      ...report.overflow.uncontained.map(
        (el) => `${report.name}: uncontained ${el.tag}.${el.className}`,
      ),
      ...report.axe.violations.map((rule) => `${report.name}: axe ${rule.id}`),
      ...report.axe.incomplete.map(
        (rule) => `${report.name}: axe incomplete ${rule.id}`,
      ),
      ...(!report.keyboard.orderMatches ? [`${report.name}: Tab order`] : []),
      ...report.keyboard.failures.map(
        (node) => `${report.name}: keyboard focus ${node.tag}#${node.id}`,
      ),
    ];
  });
  expect(pageErrors).toEqual([]);
  expect(realApiRequests).toEqual([]);
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});
