import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

describe("production demo-audit gate", () => {
  it("ships check-prod-no-demo.sh with route needles", () => {
    const script = resolve(root, "scripts/check-prod-no-demo.sh");
    expect(existsSync(script)).toBe(true);
    const body = readFileSync(script, "utf8");
    for (const needle of [
      "/demo/audit/tamper",
      "/demo/audit/restore",
      "DemoAuditPanel",
      "demoAuditApi",
    ]) {
      expect(body).toContain(needle);
    }
  });

  it("AuditPage loads DemoAuditPanel only via DEV dynamic import", () => {
    const page = readFileSync(
      resolve(root, "web/src/pages/AuditPage.tsx"),
      "utf8",
    );
    expect(page).toContain('if (!import.meta.env.DEV) return');
    expect(page).toContain('import("../components/DemoAuditPanel")');
    expect(page).not.toMatch(
      /import\s+\{\s*DemoAuditPanel\s*\}\s+from\s+"\.\.\/components\/DemoAuditPanel"/,
    );
    const real = readFileSync(resolve(root, "web/src/api/real.ts"), "utf8");
    expect(real).not.toContain("/demo/audit/");
  });
});
