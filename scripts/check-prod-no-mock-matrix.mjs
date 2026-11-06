#!/usr/bin/env node
/**
 * Build production twice (VITE_USE_MOCK unset, and forced true) into temp dirs,
 * then run check-prod-no-mock.sh against each dist. Fails if mock fixtures leak.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
const check = join(root, "scripts", "check-prod-no-mock.sh");
const checkDemo = join(root, "scripts", "check-prod-no-demo.sh");

const cases = [
  ["VITE_USE_MOCK unset", {}],
  ["VITE_USE_MOCK forced true", { VITE_USE_MOCK: "true" }],
];

const dirs = [];
let failed = 0;
try {
  for (const [label, extra] of cases) {
    const outDir = mkdtempSync(join(tmpdir(), "st143-prod-"));
    dirs.push(outDir);
    process.stdout.write(`prod-no-mock-matrix: building (${label}) → ${outDir}\n`);
    execFileSync(
      "npx",
      ["vite", "build", "--outDir", outDir, "--emptyOutDir"],
      {
        cwd: web,
        env: { ...process.env, ...extra, NODE_ENV: "production" },
        stdio: "inherit",
      },
    );
    if (!existsSync(join(outDir, "index.html"))) {
      console.error(`prod-no-mock-matrix: missing index.html for ${label}`);
      failed += 1;
      continue;
    }
    try {
      execFileSync("bash", [check, outDir], { stdio: "inherit" });
      execFileSync("bash", [checkDemo, outDir], { stdio: "inherit" });
      console.log(`prod-no-mock-matrix: OK (${label})`);
    } catch {
      console.error(`prod-no-mock-matrix: FAIL (${label})`);
      failed += 1;
    }
  }
} finally {
  for (const dir of dirs) rmSync(dir, { recursive: true, force: true });
}
if (failed) process.exit(1);
console.log("prod-no-mock-matrix: all cases passed");
