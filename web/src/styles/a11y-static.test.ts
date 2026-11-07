import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { contrastRatio } from "./contrast";

const here = dirname(fileURLToPath(import.meta.url));
const tokens = readFileSync(resolve(here, "tokens.css"), "utf8");
const shell = readFileSync(resolve(here, "../layout/shell.css"), "utf8");
const strip = readFileSync(resolve(here, "../components/DegradeStrip.tsx"), "utf8");

function rule(css: string, selector: string): string {
  const pattern = new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`);
  const found = css.match(pattern);
  expect(found, selector).toBeTruthy();
  return found?.[1] ?? "";
}

describe("declared contrast of the status strip and nearby text", () => {
  // Ratios are computed from the hex pairs in tokens.css. They do not measure
  // antialiasing, opacity, overlays, or the pixels a browser actually paints.
  it("meets 4.5:1 for the ink, brand, and risk pairs the strip and shell use", () => {
    const pairs: Array<[string, string, string]> = [
      ["ink on paper", "#1A1C1E", "#FFFFFF"],
      ["ink on canvas", "#1A1C1E", "#EEF0F3"],
      ["secondary on paper", "#3F434A", "#FFFFFF"],
      ["secondary on canvas", "#3F434A", "#EEF0F3"],
      ["muted on paper", "#5C6370", "#FFFFFF"],
      ["muted on canvas", "#5C6370", "#EEF0F3"],
      ["brand on paper", "#0F5C5C", "#FFFFFF"],
      ["brand on brand-subtle", "#0F5C5C", "#E4F2F2"],
      ["white on brand", "#FFFFFF", "#0F5C5C"],
      ["white on risk-high", "#FFFFFF", "#B42318"],
      ["risk-high on error surface", "#B42318", "#FEF3F2"],
      ["risk-low on paper", "#875A00", "#FFFFFF"],
      ["risk-low on warning surface", "#875A00", "#FFF8E6"],
      ["ink on warning surface", "#1A1C1E", "#FFF8E6"],
    ];
    for (const [name, foreground, background] of pairs) {
      expect(contrastRatio(foreground, background), name).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("stylesheet structure for the strip, targets, and motion", () => {
  it("wraps the strip and does not turn it into a three-card grid", () => {
    const row = rule(tokens, ".degrade-strip-row");
    const copy = rule(tokens, ".degrade-strip p");
    expect(row).toContain("flex-wrap: wrap");
    expect(row).not.toContain("nowrap");
    expect(copy).toContain("white-space: normal");
    expect(copy).toContain("overflow-wrap: anywhere");
    expect(tokens).not.toMatch(/\.degrade-strip[^{]*\{[^}]*grid-template-columns:\s*repeat\(3/);
    expect(tokens).toContain("@media (max-width: 420px)");
    expect(tokens).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.degrade-strip\s*\{[^}]*animation:\s*none/,
    );
  });

  it("gives navigation and primary controls a 44px minimum in CSS", () => {
    expect(rule(shell, ".nav-item")).toContain("min-height: 44px");
    expect(rule(tokens, ".flow-trail-link")).toContain("min-height: 44px");
    expect(rule(tokens, ".btn")).toContain("min-height: 44px");
    expect(rule(tokens, ".input,\n.select")).toContain("min-height: 44px");
  });

  it("does not make the strip focusable and does not move focus from it", () => {
    expect(strip).not.toMatch(/tabIndex|autoFocus|\.focus\(/);
  });
});
