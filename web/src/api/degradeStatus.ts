import type { ModelEntry, ModelTrace } from "./types";
import { degradeStatusText } from "./provenance";

/**
 * Per-capability degrade view built only from fields that endpoint actually returns.
 * Extraction and review use degrade_level / degrade_status / llm_verified plus their
 * own model traces. Chat messages have traces only (no degrade fields). System health
 * is /system/models alone. Callers cannot pass another capability's payload in.
 */

export type DegradeLevel = "L0" | "L1" | "L2" | "L3";
export type Capability = "extraction" | "review" | "chat" | "system";
export type LimitKey = DegradeLevel | "unconfirmed" | "inconsistent";

export type ProvenanceView = {
  capability: Capability;
  /** Same as capability. Names the scope sentence so health and history stay distinct. */
  scope: Capability;
  level:
    | { kind: "known"; level: DegradeLevel }
    | { kind: "missing" }
    | { kind: "unrecognized" };
  /** Wire degrade_status. Null when that field is absent or not on this payload. */
  serverStatus: string | null;
  /** Absent when this payload has no llm_verified field, or the value is not boolean. */
  llmVerified: true | false | "absent";
  source:
    | { kind: "none" }
    | {
        kind: "trace";
        provider: string;
        model: string;
        status: "ok" | "fallback" | "failed";
        local: boolean;
      }
    | {
        kind: "health";
        provider: string;
        model: string;
        deployment: "local" | "cloud";
        local: boolean;
      };
  limits: LimitKey[];
  /** True only when this payload's own trace or health entry is a local/ollama model. */
  localCaveat: boolean;
  /** Product positioning is not a measured level. Shown on system health only. */
  positioning: boolean;
  blocked: boolean;
  /** Configured provider order from /system/models, not evidence of what a run used. */
  chain: string[] | null;
};

const LEVELS: readonly DegradeLevel[] = ["L0", "L1", "L2", "L3"];

export function readLevel(value: unknown): ProvenanceView["level"] {
  if (typeof value !== "string") return { kind: "missing" };
  if ((LEVELS as readonly string[]).includes(value)) {
    return { kind: "known", level: value as DegradeLevel };
  }
  // Whitespace or unknown tokens are not coerced (so " L0 " is not treated as L0).
  if (value.trim() === "") return { kind: "missing" };
  return { kind: "unrecognized" };
}

function hasControlChar(text: string): boolean {
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code <= 31 || code === 127) return true;
  }
  return false;
}

function cleanName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || text.length > 80 || hasControlChar(text)) return null;
  return text;
}

function cleanStatus(value: unknown): "ok" | "fallback" | "failed" | null {
  return value === "ok" || value === "fallback" || value === "failed" ? value : null;
}

function isLocal(provider: string, deployment?: string): boolean {
  return provider === "ollama" || deployment === "local";
}

function traceSource(models: unknown): ProvenanceView["source"] {
  if (!Array.isArray(models)) return { kind: "none" };
  const traces: Array<{
    provider: string;
    model: string;
    status: "ok" | "fallback" | "failed";
    local: boolean;
  }> = [];
  for (const item of models) {
    if (!item || typeof item !== "object") continue;
    const row = item as Partial<ModelTrace>;
    if (row.category !== "llm") continue;
    const provider = cleanName(row.provider);
    const model = cleanName(row.model);
    const status = cleanStatus(row.status);
    if (!provider || !model || !status) continue;
    traces.push({ provider, model, status, local: isLocal(provider) });
  }
  const served = [...traces].reverse().find((row) => row.status === "ok" || row.status === "fallback");
  const pick = served ?? traces[traces.length - 1];
  if (!pick) return { kind: "none" };
  return { kind: "trace", ...pick };
}

function healthSource(models: unknown): ProvenanceView["source"] {
  if (!Array.isArray(models)) return { kind: "none" };
  for (const item of models) {
    if (!item || typeof item !== "object") continue;
    const row = item as Partial<ModelEntry>;
    if (row.category !== "llm" || row.healthy !== true) continue;
    const provider = cleanName(row.provider);
    const model = cleanName(row.model);
    const deployment = row.deployment === "local" || row.deployment === "cloud" ? row.deployment : null;
    if (!provider || !model || !deployment) continue;
    // Backend selects the first healthy LLM. Do not promote a later entry.
    return {
      kind: "health",
      provider,
      model,
      deployment,
      local: isLocal(provider, deployment),
    };
  }
  return { kind: "none" };
}

function readChain(value: unknown): string[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const names: string[] = [];
  for (const item of value) {
    const name = cleanName(item);
    if (!name) return null;
    names.push(name);
  }
  return names;
}

function readVerified(value: unknown): true | false | "absent" {
  if (value === true) return true;
  if (value === false) return false;
  return "absent";
}

export function limitsFor(
  level: ProvenanceView["level"],
  source: ProvenanceView["source"],
): LimitKey[] {
  if (level.kind !== "known") return ["unconfirmed"];
  const local = source.kind !== "none" && source.local;
  const cloudSource = source.kind !== "none" && !source.local;
  const served =
    source.kind === "trace" && (source.status === "ok" || source.status === "fallback");
  const limits: LimitKey[] = [level.level];
  if (level.level === "L3" && served) limits.push("inconsistent");
  if ((level.level === "L0" || level.level === "L1") && local) limits.push("inconsistent");
  if (level.level === "L2" && cloudSource) limits.push("inconsistent");
  return limits;
}

function finish(
  partial: Omit<ProvenanceView, "limits" | "localCaveat">,
): ProvenanceView {
  const localCaveat = partial.source.kind !== "none" && partial.source.local;
  return {
    ...partial,
    limits: limitsFor(partial.level, partial.source),
    localCaveat,
  };
}

export function recordProvenance(
  capability: "extraction" | "review",
  record: {
    degrade_level?: unknown;
    degrade_status?: unknown;
    llm_verified?: unknown;
    models?: unknown;
  },
): ProvenanceView {
  const rawStatus = record.degrade_status;
  return finish({
    capability,
    scope: capability,
    level: readLevel(record.degrade_level),
    serverStatus: degradeStatusText({
      degrade_status: typeof rawStatus === "string" ? rawStatus : null,
    }),
    llmVerified: readVerified(record.llm_verified),
    source: traceSource(record.models),
    positioning: false,
    blocked: false,
    chain: null,
  });
}

/** Chat wire has role, blocked, and models. degrade_level is not a message field and is ignored. */
export function chatProvenance(message: {
  role?: unknown;
  blocked?: unknown;
  models?: unknown;
}): ProvenanceView | null {
  if (message.role !== "assistant") return null;
  return finish({
    capability: "chat",
    scope: "chat",
    level: { kind: "missing" },
    serverStatus: null,
    llmVerified: "absent",
    source: traceSource(message.models),
    positioning: false,
    blocked: message.blocked === true,
    chain: null,
  });
}

export function systemProvenance(chain: {
  degrade_level?: unknown;
  llm_provider_chain?: unknown;
  models?: unknown;
}): ProvenanceView {
  return finish({
    capability: "system",
    scope: "system",
    level: readLevel(chain.degrade_level),
    serverStatus: null,
    llmVerified: "absent",
    source: healthSource(chain.models),
    positioning: true,
    blocked: false,
    chain: readChain(chain.llm_provider_chain),
  });
}
