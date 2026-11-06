import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "real-backend.spec.ts",
  timeout: 240_000,
  expect: { timeout: 30_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results-real",
  use: {
    baseURL: "https://localhost:5173",
    browserName: "chromium",
    headless: true,
    ignoreHTTPSErrors: true,
    reducedMotion: "reduce",
    locale: "zh-CN",
    timezoneId: "America/Tijuana",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "390", use: { viewport: { width: 390, height: 844 } } },
    { name: "1440", use: { viewport: { width: 1440, height: 900 } } },
  ],
  // Dev server is started externally without VITE_USE_MOCK.
  webServer: {
    command: "node -e \"process.exit(0)\"",
    url: "https://localhost:5173",
    ignoreHTTPSErrors: true,
    reuseExistingServer: true,
    timeout: 5_000,
  },
});
