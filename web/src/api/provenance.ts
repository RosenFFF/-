import type { Review } from "./types";

export function sourceKind(value: unknown): "synthetic" | "public" | null {
  return value === "synthetic" || value === "public" ? value : null;
}
export function sourceText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
// Never turn backend-provided javascript/data/credential-bearing URLs into links.
export function sourceUrl(value: unknown): string | null {
  const text = sourceText(value);
  if (!text) return null;
  try {
    const url = new URL(text);
    return ["https:", "http:"].includes(url.protocol) &&
      url.hostname &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}
export function verificationKey(
  report: Pick<Review, "degrade_level" | "llm_verified">,
): string {
  if (report.degrade_level === "L3") return "report.verification.L3";
  // A contradictory/older response must not claim LLM validation succeeded.
  if (report.llm_verified === false) return "report.verification.unverified";
  return ["L0", "L1", "L2"].includes(report.degrade_level)
    ? `report.verification.${report.degrade_level}`
    : "report.verification.unknown";
}
