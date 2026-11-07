import { test, expect } from "@playwright/test";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { safeHarEntry, summarizeSse } from "../config/demo-evidence.ts";

if (process.env.ST143_DEMO_MACHINE !== "1") {
  throw new Error("This acceptance test is restricted to the approved demonstration machine");
}

// No fixture, mock routing, stored auth state, model key or automatic retry.
test("production UI: login, upload, review and three successful SSE follow-ups", async ({ page, context }) => {
  const root = resolve(process.env.ST143_DEMO_RUN_DIR!, "evidence");
  await mkdir(root); // Fail rather than overwrite a previous archive.
  const username = process.env.ST143_DEMO_USERNAME;
  const password = process.env.ST143_DEMO_PASSWORD;
  const pdf = process.env.ST143_DEMO_SAMPLE_PDF;
  if (!username || !password || !pdf) throw new Error("Set demo account and synthetic PDF environment variables");
  const pdfBytes = await readFile(pdf);
  const har: ReturnType<typeof safeHarEntry>[] = [];
  const counts = { consoleErrors: 0, pageErrors: 0, networkFailures: 0, httpErrors: 0 };
  const rounds: { round: number; broad: boolean; httpStatus: number; elapsedMs: number; stream: ReturnType<typeof summarizeSse> }[] = [];
  let stage = "login";
  let passed = false;
  let authenticated = false;
  let tracing = false;
  let traceSafe = false;
  const temp = await mkdtemp(resolve(tmpdir(), "st143-demo-private-"));
  await chmod(temp, 0o700);
  const screenshot = async (name: string) => {
    await expect(page.locator(".mock-banner")).toHaveCount(0);
    await page.screenshot({ path: resolve(root, `${name}.png`), fullPage: true });
  };
  page.on("console", (message) => { if (message.type() === "error") counts.consoleErrors++; });
  page.on("pageerror", () => { counts.pageErrors++; });
  page.on("requestfailed", () => { counts.networkFailures++; });
  page.on("response", (response) => {
    if (response.status() >= 400) counts.httpErrors++;
    har.push(safeHarEntry(response.url(), response.request().method(), response.status(), response.headers()["content-type"] ?? ""));
  });
  try {
    await page.goto("/login");
    await screenshot("01-login-empty");
    try {
      await page.locator('input[autocomplete="username"]').fill(username);
      await page.locator('input[autocomplete="current-password"]').fill(password);
      await page.getByRole("button", { name: "登录", exact: true }).click();
      await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 30_000 });
    } catch { throw new Error("Login failed; account values and raw action logs omitted"); }
    authenticated = true;
    // Never trace credential entry. Network records will be removed before publication.
    await context.tracing.start({ screenshots: true, snapshots: false, sources: false });
    tracing = true;
    await screenshot("02-logged-in");
    stage = "upload";
    await page.goto("/cases/new");
    await page.locator('input[type="file"]').setInputFiles({ name: "demo-invoice.pdf", mimeType: "application/pdf", buffer: pdfBytes });
    await screenshot("03-upload-selected");
    await page.getByRole("button", { name: "开始识别", exact: true }).click();
    await page.waitForURL(/\/cases\/[^/]+\/extract/, { timeout: 180_000 });
    await expect(page.locator(".report-verification")).toBeVisible();
    await screenshot("04-extracted");
    const docId = new URL(page.url()).pathname.match(/cases\/([^/]+)/)?.[1];
    expect(docId).toBeTruthy();
    stage = "review";
    await page.goto(`/cases/${docId}/report`);
    await page.getByRole("button", { name: "发起审查", exact: true }).click();
    const ask = page.getByRole("link", { name: "继续追问", exact: true });
    await expect(ask).toBeVisible();
    const reviewId = new URL((await ask.getAttribute("href"))!, page.url()).searchParams.get("review");
    expect(reviewId).toBeTruthy();
    const reportResponse = await context.request.get(`/api/v1/reviews/${encodeURIComponent(reviewId!)}?language=zh-CN`);
    expect(reportResponse.ok()).toBe(true);
    const report = await reportResponse.json() as { status: string; summary?: string; degrade_level: string; llm_verified?: boolean };
    expect(report.status).toBe("completed");
    expect(report.summary?.trim().length).toBeGreaterThan(0);
    expect(report.degrade_level).toBe("L0");
    expect(report.llm_verified).toBe(true);
    await screenshot("05-review-conclusion");
    await ask.click();
    const box = page.getByRole("textbox", { name: "例如：如何修改才能合规？" });
    const questions = ["金额不一致应如何处理？", "请全面分析这份单证的主要合规风险并给出修改建议。", "请依据本次报告引用的条款，说明最优先修改的事项。"];
    for (const [index, question] of questions.entries()) {
      stage = `follow-up-${index + 1}`;
      await expect(box).toBeEnabled();
      const previous = await page.locator(".chat-message.assistant").count();
      await box.fill(question);
      const responsePromise = page.waitForResponse((r) => /\/reviews\/[^/]+\/messages$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
      const start = Date.now();
      await page.getByRole("button", { name: "发送", exact: true }).click();
      const response = await responsePromise;
      expect(response.status()).toBe(200);
      expect(response.headers()["content-type"]).toContain("text/event-stream");
      await expect(box).toBeEnabled();
      const stream = summarizeSse((await response.body()).toString("utf8"));
      rounds.push({ round: index + 1, broad: index === 1, httpStatus: response.status(), elapsedMs: Date.now() - start, stream });
      // Preserve failure evidence before assertion; HTTP 200 with an error event is a real failure.
      await screenshot(`0${index + 6}-follow-up-${index + 1}`);
      expect(stream.success).toBe(true);
      await expect(page.locator(".chat-message.assistant")).toHaveCount(previous + 1);
      await expect(page.locator(".chat-message.assistant").last()).not.toHaveClass(/blocked/);
      await expect(page.locator(".chat-message.assistant").last()).not.toHaveText("");
      await expect(page.locator(".error-notice")).toHaveCount(0);
    }
    expect(counts).toEqual({ consoleErrors: 0, pageErrors: 0, networkFailures: 0, httpErrors: 0 });
    passed = true;
  } catch {
    if (authenticated) await screenshot("99-failed-stage").catch(() => {});
    // Do not echo raw browser errors, URLs, account values or network payloads.
    throw new Error(`Demo acceptance failed at ${stage}; see sanitized summary and screenshots`);
  } finally {
    try {
      if (tracing) {
        const raw = resolve(temp, "private-trace.zip");
        await context.tracing.stop({ path: raw });
        await chmod(raw, 0o600);
        execFileSync("python3", ["scripts/sanitize-demo-trace.py", raw, resolve(root, "trace-sanitized.zip")], { stdio: "ignore" });
        traceSafe = true;
      }
    } finally {
      await rm(temp, { recursive: true, force: true });
      await writeFile(resolve(root, "network-sanitized.har"), JSON.stringify({ log: { version: "1.2", creator: { name: "ST143 metadata-only evidence", version: "1" }, entries: har } }, null, 2));
      await writeFile(resolve(root, "summary.json"), JSON.stringify({
        evidence: "Playwright 无头 Chromium 实测（仅运行后成立）", frontendMode: "production dist via Vite preview; mock disabled",
        frontend: process.env.ST143_DEMO_FRONTEND_URL, backend: process.env.ST143_DEMO_BACKEND_URL,
        frontendCommit: process.env.ST143_DEMO_FRONTEND_COMMIT ?? "not supplied", backendCommit: process.env.ST143_DEMO_BACKEND_COMMIT ?? "not supplied",
        passed: passed && traceSafe, stage, rounds, counts, traceSanitized: traceSafe,
        har: "metadata only; no bodies, headers, cookies or query; timing fields placeholders, not performance data",
        trace: "visual/action-only, recorded after login; network, DOM snapshots, source and action values removed",
        capturedAt: new Date().toISOString(),
      }, null, 2));
    }
  }
});
