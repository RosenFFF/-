import { test, expect, request as playwrightRequest } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const output =
  process.env.M1_SCREENSHOT_DIR ??
  fileURLToPath(new URL("../../../screenshots/m1/", import.meta.url));

// Checked-in synthetic test accounts from backend tests.conftest — not user secrets.
const REVIEWER = {
  username: "reviewer",
  password: "reviewer-pass-123456",
};
const REVIEWER2 = {
  username: "reviewer2",
  password: "reviewer2-pass-123456",
};

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

  await page.locator('input[autocomplete="username"]').fill(REVIEWER.username);
  await page
    .locator('input[autocomplete="current-password"]')
    .fill(REVIEWER.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), {
    timeout: 30_000,
  });

  await page.goto("/cases/new");
  await expect(page.getByRole("heading", { name: "上传单证" })).toBeVisible();
  await shot("upload");

  await page.locator('input[type="file"]').setInputFiles({
    name: "invoice.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
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
  await expect(page.locator(".citation-source").first()).toContainText(
    "无公开来源",
  );
  await shot("report");

  // Capture review id from continue-ask link.
  const askLink = page.getByRole("link", { name: "继续追问", exact: true });
  const href = await askLink.getAttribute("href");
  expect(href).toBeTruthy();
  const reviewId = new URL(href!, "https://localhost").searchParams.get(
    "review",
  );
  expect(reviewId).toBeTruthy();

  await askLink.click();
  await expect(
    page.getByRole("textbox", { name: "例如：如何修改才能合规？" }),
  ).toBeEnabled({ timeout: 30_000 });
  await page
    .getByRole("textbox", { name: "例如：如何修改才能合规？" })
    .fill("金额不一致应如何处理？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  // No real model in this environment → clear MODEL_UNAVAILABLE / error notice.
  // Do not expect a fabricated assistant answer.
  await expect(page.locator(".error-notice")).toContainText(
    /模型暂不可用|Model unavailable|Mô hình chưa khả dụng/,
    { timeout: 90_000 },
  );
  // Model failure persists the user turn only — no fabricated assistant success.
  await expect(page.locator(".chat-message.assistant")).toHaveCount(0);
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await expect(page.getByText("MOCK ·")).toHaveCount(0);
  await shot("ask");

  // Cross-user: reviewer2 must not read history or replay Last-Event-ID for reviewer1's review.
  const other = await playwrightRequest.newContext({
    baseURL: "https://localhost:5173",
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { Origin: "https://localhost:5173" },
  });
  const login = await other.post("/api/v1/auth/login", {
    data: REVIEWER2,
    headers: { Origin: "https://localhost:5173" },
  });
  expect(login.status()).toBe(200);
  const csrf = (await login.headersArray())
    .filter((h) => h.name.toLowerCase() === "set-cookie")
    .map((h) => /csrf_token=([^;]+)/.exec(h.value)?.[1])
    .find(Boolean);
  expect(csrf).toBeTruthy();
  const history = await other.get(`/api/v1/reviews/${reviewId}/messages`);
  expect([403, 404]).toContain(history.status());
  const replay = await other.post(`/api/v1/reviews/${reviewId}/messages`, {
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      "X-CSRF-Token": decodeURIComponent(csrf!),
      "Last-Event-ID": "11111111-1111-4111-8111-111111111111:0",
      Origin: "https://localhost:5173",
    },
    data: { content: "金额不一致应如何处理？", language: "zh-CN" },
  });
  expect([403, 404]).toContain(replay.status());
  await other.dispose();

  await writeFile(
    resolve(output, `real-meta-${size}.json`),
    JSON.stringify(
      {
        backend: "40809ef",
        viewport: size,
        documentId: docId,
        reviewId,
        mockBanner: await page.locator(".mock-banner").count(),
        ask: "MODEL_UNAVAILABLE_or_error_no_fabricated_success",
        crossUserHistory: history.status(),
        crossUserReplay: replay.status(),
        realModel: "blocked_no_live_llm",
        testStandIn: "fixture_accounts_isolated_sqlite_fakeredis",
      },
      null,
      2,
    ),
  );
});
