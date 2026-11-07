import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
import { resolveApiProxyTarget } from "./config/api-proxy.ts";

if (process.env.ST143_DEMO_MACHINE !== "1") {
  throw new Error("Demo-machine execution only; do not run on the policy-blocked platform computer");
}
function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}
const frontend = resolveApiProxyTarget(required("ST143_DEMO_FRONTEND_URL"));
const backend = resolveApiProxyTarget(required("ST143_DEMO_BACKEND_URL"));
const url = new URL(frontend);
if (url.protocol !== "https:") throw new Error("Demo frontend must use trusted HTTPS");
if (process.env.VITE_USE_MOCK === "true") throw new Error("Mock must be disabled");
const host = url.hostname.replace(/^\[|\]$/g, "");
export default defineConfig({
  testDir: "./e2e", testMatch: "demo-machine.spec.ts",
  timeout: 900_000, expect: { timeout: 180_000 },
  workers: 1, fullyParallel: false, retries: 0,
  reporter: [["list"]], outputDir: resolve(required("ST143_DEMO_RUN_DIR"), "runner"),
  use: {
    baseURL: frontend, browserName: "chromium", headless: true,
    ignoreHTTPSErrors: false, locale: "zh-CN", timezoneId: "America/Tijuana",
    viewport: { width: 1440, height: 900 }, reducedMotion: "reduce",
    trace: "off", screenshot: "off", video: "off",
  },
  webServer: {
    command: `npm run preview -- --host ${host} --port ${url.port || "443"} --strictPort`,
    url: frontend, ignoreHTTPSErrors: false, reuseExistingServer: false,
    env: { ST143_API_PROXY_TARGET: backend, VITE_USE_MOCK: "false" },
    timeout: 30_000,
  },
});
