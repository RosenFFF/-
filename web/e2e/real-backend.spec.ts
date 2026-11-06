import { test, expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const output =
  process.env.M1_SCREENSHOT_DIR ??
  fileURLToPath(new URL("../../../screenshots/m1/", import.meta.url));

// Checked-in synthetic test account from backend tests.conftest — not a user secret.
const PASSWORD = "reviewer-pass-123456";

test("real backend screenshots without MOCK banner", async ({ page }, info) => {
  const size = info.project.name;
  await mkdir(output, { recursive: true });
  const shot = async (name: string) => {
    await page.screenshot({
      path: resolve(output, `real-${name}-${size}.png`),
      fullPage: true,
    });
  };
  const pdf = await readFile(resolve(output, "_real-invoice.pdf"));

  await page.goto("/login");
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await shot("login");

  await page.locator('input[autocomplete="username"]').fill("reviewer");
  await page.locator('input[autocomplete="current-password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), {
    timeout: 30_000,
  });
  await expect(page.locator(".mock-banner")).toHaveCount(0);

  await page.goto("/cases/new");
  await expect(page.getByRole("heading", { name: "上传单证" })).toBeVisible();
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await shot("upload");

  await page.locator('input[type="file"]').setInputFiles({
    name: "invoice.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await expect(
    page.getByRole("button", { name: "开始识别", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  // UploadPage polls then navigates to extract automatically.
  await page.waitForURL(/\/cases\/[^/]+\/extract/, { timeout: 180_000 });

  await expect(page.locator(".report-verification")).toContainText(
    "规则引擎回退，未完成真实 LLM 验证",
    { timeout: 60_000 },
  );
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await shot("extract");

  const match = page.url().match(/cases\/([^/?#]+)/);
  expect(match).toBeTruthy();
  const docId = match![1];

  await page.goto(`/cases/${docId}/report`);
  await page.getByRole("button", { name: "发起审查", exact: true }).click();
  await expect(page.locator(".report-verification")).toContainText(
    "规则引擎回退，未完成真实 LLM 验证",
    { timeout: 120_000 },
  );
  await expect(page.locator(".report-rule-source")).toContainText(
    "合成规则 · 非真实合规结论",
  );
  // Citation provenance is visible even before opening rule detail.
  await expect(page.locator(".citation-source").first()).toContainText(
    "合成规则 · 非真实合规结论",
  );
  await expect(page.locator(".citation-source").first()).toContainText(
    "无公开来源",
  );
  await expect(page.locator(".citation-source").first()).toContainText(
    "版本未提供",
  );
  const citationOpen = page.locator("button.btn.btn-secondary").filter({
    hasText: "·",
  }).first();
  await citationOpen.click();
  await expect(page.locator(".rule-text")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".rule-text .citation-source")).toContainText(
    "合成规则 · 非真实合规结论",
  );
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await shot("report");

  // GET/POST messages are both 501 until real LLM is available; input stays disabled.
  await page.getByRole("link", { name: "继续追问", exact: true }).click();
  await expect(page.getByText("功能暂未实现")).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByRole("textbox", { name: "例如：如何修改才能合规？" }),
  ).toBeDisabled();
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await shot("ask-501");

  await writeFile(
    resolve(output, `real-meta-${size}.json`),
    JSON.stringify(
      {
        backend: "8d94e02",
        viewport: size,
        documentId: docId,
        mockBanner: await page.locator(".mock-banner").count(),
      },
      null,
      2,
    ),
  );
});
