import { describe, expect, it } from "vitest";
import { modelDisplay, noHealthyLlm } from "./modelStatus";
import type { ModelChain } from "./types";

// Shape mirrors backend 831cbe8 reports/progress/backend-llm-e2e/model-probe.json (L3, 3 LLMs unhealthy).
const probe: ModelChain = {
  degrade_level: "L3",
  llm_provider_chain: ["deepseek", "qwen", "ollama"],
  models: [
    { category: "ocr", provider: "local", model: "rapidocr-ppocrv4", deployment: "local", stage: "单证识别", healthy: true },
    { category: "llm", provider: "deepseek", model: "deepseek-chat", deployment: "cloud", stage: "s", healthy: false },
    { category: "llm", provider: "qwen", model: "qwen-plus", deployment: "cloud", stage: "s", healthy: false },
    { category: "llm", provider: "ollama", model: "qwen2.5:0.5b", deployment: "local", stage: "s", healthy: false },
    {
      category: "embedding", provider: "local", model: "feature-hash-128 (lightweight, not BGE)", deployment: "local", stage: "规则检索",
      healthy: true, lightweight: true, retrieval_mode: "lightweight_hash", implementation_mode: "lightweight_hash",
      mode_label: "轻量回退（非 BGE 神经模型）", configured_model: "BAAI/bge-m3",
    },
  ],
};

describe("model status from the live wire", () => {
  it("reports no healthy LLM when all three are unhealthy at L3", () => {
    expect(noHealthyLlm(probe)).toBe(true);
  });
  it("is false once any LLM is healthy", () => {
    const ok = { ...probe, models: probe.models.map((m) => (m.provider === "ollama" ? { ...m, healthy: true } : m)) };
    expect(noHealthyLlm(ok)).toBe(false);
  });
  it("never presents the lightweight retrieval as BGE", () => {
    const d = modelDisplay(probe.models[4]);
    expect(d.name).not.toMatch(/^BAAI|bge-m3$/i);
    expect(d.name).toContain("not BGE");
    expect(d.note).toBe("轻量回退（非 BGE 神经模型）");
  });
});
