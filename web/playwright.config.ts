import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: /(?:real-(?:backend|audit|demo)|demo-machine)\.spec\.ts/,
  timeout: 180_000,
  expect: { timeout: 10_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL: "https://localhost:5173",
    browserName: "chromium",
    headless: true,
    // Scoped to this local, self-signed development server; never production.
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
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    env: { VITE_USE_MOCK: "true" },
    url: "https://localhost:5173",
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 3000 },
  },
});
