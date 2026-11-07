import type { ModelChain, ModelEntry } from "./types";

/** True when the wire reports no healthy LLM (all llm entries healthy=false or none). */
export function noHealthyLlm(chain: ModelChain): boolean {
  return !chain.models.some((m) => m.category === "llm" && m.healthy);
}

/**
 * Label for a model row. Lightweight embedding/reranker fallbacks are shown by
 * their wire `model` + `mode_label`; `configured_model` (e.g. BAAI/bge-m3) is the
 * intended model, NOT what runs, so it is never used as the displayed name.
 */
export function modelDisplay(m: ModelEntry): { name: string; note: string | null } {
  return { name: m.model, note: m.lightweight ? (m.mode_label ?? "lightweight") : (m.mode_label ?? null) };
}
