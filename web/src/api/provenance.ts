import type { SourceMetadata } from "./types";

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

/** Prefer the wire label; never invent copy from source_kind alone. */
export function sourceKindLabel(value: SourceMetadata): string | null {
  return sourceText(value.source_kind_label);
}

/** Render degrade_status from the response only; missing → null (UI shows 状态信息缺失). */
export function degradeStatusText(
  report: { degrade_status?: string | null },
): string | null {
  return sourceText(report.degrade_status);
}

export function excerptKind(
  value: unknown,
): "summary" | "verbatim" | null {
  return value === "summary" || value === "verbatim" ? value : null;
}

export function applicability(value: unknown): "unverified" | null {
  return value === "unverified" ? value : null;
}
