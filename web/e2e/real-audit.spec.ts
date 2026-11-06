import { test, expect, request as playwrightRequest } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const output =
  process.env.M3_SCREENSHOT_DIR ??
  process.env.M2_SCREENSHOT_DIR ??
  fileURLToPath(new URL("../../../screenshots/m3/", import.meta.url));

/** Fixture accounts from backend tests.conftest — not user secrets. */
const ACCOUNTS = {
  admin: { username: "admin", password: "admin-pass-123456" },
  auditor: { username: "auditor", password: "auditor-pass-123456" },
  reviewer: { username: "reviewer", password: "reviewer-pass-123456" },
  reviewer2: { username: "reviewer2", password: "reviewer2-pass-123456" },
} as const;

const INFRA = {
  kind: "real_backend_fixture",
  database: "sqlite_stand_in",
  redis: "fakeredis_stand_in",
  postgres_live: false,
  redis_live: false,
  note: "Not claiming DB-level tenant isolation or live Postgres migration acceptance; backend skipped live Postgres tests.",
  backend_commit: "87ff58c",
  real_model: "blocked",
  demo_routes: "fixture_only_DEMO_MODE_env_not_prod",
  frontend_prod_demo_entry: "stripped_checked_by_check-prod-no-demo.sh",
} as const;

test("real audit dashboard: admin/auditor/reviewer-403/rate-limited + cross-tenant", async ({
  page,
}, info) => {
  const size = info.project.name;
  await mkdir(output, { recursive: true });
  const meta: Record<string, unknown> = {
    ...INFRA,
    viewport: size,
    mockBanner: 0,
  };

  const shot = async (name: string, extra: Record<string, unknown> = {}) => {
    const base = `real-audit-${name}-${size}`;
    await page.screenshot({
      path: resolve(output, `${base}.png`),
      fullPage: true,
    });
    await writeFile(
      resolve(output, `${base}.json`),
      JSON.stringify({ ...meta, ...extra, screenshot: `${base}.png` }, null, 2),
    );
  };

  const signIn = async (role: keyof typeof ACCOUNTS) => {
    await page.goto("/login");
    await expect(page.locator(".mock-banner")).toHaveCount(0);
    await page.locator('input[autocomplete="username"]').fill(ACCOUNTS[role].username);
    await page
      .locator('input[autocomplete="current-password"]')
      .fill(ACCOUNTS[role].password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => !url.pathname.includes("/login"), {
      timeout: 30_000,
    });
  };

  const signOut = async () => {
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await expect(page).toHaveURL(/\/login$/);
  };

  // --- reviewer 403 ---
  await signIn("reviewer");
  await page.goto("/audit");
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await expect(page.locator(".banner.error-notice, .error-notice")).toContainText(
    /403|权限|拒绝|PERMISSION/i,
  );
  await page.getByRole("button", { name: "全局看板", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(/403|权限|拒绝/i);
  await shot("reviewer-403", { role: "reviewer", expect: "403_on_stats_and_logs" });
  await signOut();

  // --- auditor can read ---
  await signIn("auditor");
  await page.goto("/audit");
  await expect(page.locator(".mock-banner")).toHaveCount(0);
  await expect(page.getByText("未完成真实 LLM 验证")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".audit-metric").first()).toBeVisible();
  await page.getByRole("button", { name: "全局看板", exact: true }).click();
  await expect(page.locator(".table, .empty-message").first()).toBeVisible();
  await shot("auditor", { role: "auditor", expect: "stats_and_logs_readable" });
  await signOut();

  // --- admin: stats, verify, demo tamper/restore on isolated fixture ---
  await signIn("admin");
  await page.goto("/audit");
  await expect(page.getByText("未完成真实 LLM 验证")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("已完成", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "全局看板", exact: true }).click();
  await page.getByRole("button", { name: "校验哈希链", exact: true }).click();
  await expect(page.locator(".banner").filter({ hasText: /审计链/ })).toBeVisible();

  const logInput = page.getByLabel("审计日志 ID");
  await expect(logInput).toBeVisible({ timeout: 15_000 });

  const ctx = await playwrightRequest.newContext({
    baseURL: "https://localhost:5173",
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { Origin: "https://localhost:5173" },
  });
  const login = await ctx.post("/api/v1/auth/login", {
    data: ACCOUNTS.admin,
    headers: { Origin: "https://localhost:5173" },
  });
  expect(login.status()).toBe(200);
  const logs = await ctx.get("/api/v1/audit/logs?result=denied&page_size=5");
  expect(logs.status()).toBe(200);
  const items = (await logs.json()).items as { id: string }[];
  expect(items.length).toBeGreaterThan(0);
  const logId = items[0].id;
  await logInput.fill(logId);

  await page.getByRole("button", { name: "篡改（不重算哈希）", exact: true }).click();
  await expect(page.getByText(/tampered_id=/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".banner")).toContainText(/断点|不完整|broken/i);
  await page.getByRole("button", { name: "恢复原文", exact: true }).click();
  await expect(page.getByText(/restored_id=/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".banner")).toContainText(/完整/);
  await shot("admin", {
    role: "admin",
    expect: "stats_verify_demo_tamper_restore",
    demoLogId: logId,
    demoData: "isolated_fixture_sqlite_fakeredis_only",
  });

  // cross-tenant / cross-user rejection (API)
  const other = await playwrightRequest.newContext({
    baseURL: "https://localhost:5173",
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { Origin: "https://localhost:5173" },
  });
  const otherLogin = await other.post("/api/v1/auth/login", {
    data: ACCOUNTS.reviewer2,
    headers: { Origin: "https://localhost:5173" },
  });
  expect(otherLogin.status()).toBe(200);
  const deniedStats = await other.get("/api/v1/audit/stats");
  expect(deniedStats.status()).toBe(403);
  const foreignAudit = await other.get(
    "/api/v1/reviews/00000000-0000-4000-8000-000000000001/audit",
  );
  expect([403, 404]).toContain(foreignAudit.status());
  meta.crossTenant = {
    reviewer2_stats: deniedStats.status(),
    fake_review_audit: foreignAudit.status(),
  };
  await other.dispose();
  await ctx.dispose();

  // --- rate-limited: burn write bucket from the same browser session (no auto-retry) ---
  const demoStatuses: number[] = [];
  page.on("response", (res) => {
    if (res.url().includes("/demo/audit/")) demoStatuses.push(res.status());
  });
  // Fixture rl_default_per_min=2; admin section already used tamper+restore (=2). Next write → 429.
  for (const name of ["恢复原文", "篡改（不重算哈希）", "恢复原文"] as const) {
    if (await page.locator(".audit-demo .audit-rate-limit").isVisible()) break;
    const btn = page.getByRole("button", { name, exact: true });
    if (await btn.isEnabled()) await btn.click();
    await page.waitForTimeout(400);
  }
  await expect(page.locator(".audit-demo .audit-rate-limit")).toContainText(
    /限流|Rate limited|giới hạn|过于频繁|RATE_LIMITED/i,
    { timeout: 15_000 },
  );
  await expect(page.locator(".audit-demo .audit-countdown")).toBeVisible();
  await page.waitForTimeout(1200);
  await expect(page.locator(".audit-demo .audit-rate-limit")).toBeVisible();
  await shot("rate-limited", {
    role: "admin",
    expect: "429_retry_after_countdown_no_auto_retry",
    demoStatuses,
  });

  await writeFile(
    resolve(output, `real-audit-summary-${size}.json`),
    JSON.stringify({ ...meta, size }, null, 2),
  );
});
