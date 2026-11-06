import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi, afterEach } from "vitest";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const checkScript = resolve(root, "scripts/check-prod-no-mock.sh");
const matrixScript = resolve(root, "scripts/check-prod-no-mock-matrix.mjs");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("production mock gate", () => {
  it("ships check-prod-no-mock.sh and matrix runner", () => {
    expect(existsSync(checkScript)).toBe(true);
    expect(existsSync(matrixScript)).toBe(true);
    const body = readFileSync(checkScript, "utf8");
    for (const needle of [
      "MOCK 数据 · 仅开发",
      "DEVELOPMENT ONLY",
      "MOCK · 开发用合规报告",
      "mockApi",
      "VITE_USE_MOCK",
      "sr_mock_user",
    ]) {
      expect(body).toContain(needle);
    }
  });

  it("useMock stays false when DEV is false even if VITE_USE_MOCK=true", async () => {
    vi.resetModules();
    vi.stubEnv("DEV", "false");
    vi.stubEnv("VITE_USE_MOCK", "true");
    // Vite replaces import.meta.env at transform time; in vitest we assert source contract.
    const source = readFileSync(
      resolve(root, "web/src/api/index.ts"),
      "utf8",
    );
    expect(source).toMatch(
      /export const useMock =\s*import\.meta\.env\.DEV && import\.meta\.env\.VITE_USE_MOCK === "true"/,
    );
    expect(source).toContain('await import("../mock/api")');
  });
});
