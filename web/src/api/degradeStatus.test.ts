import { describe, expect, it } from "vitest";
import {
  chatProvenance,
  readLevel,
  recordProvenance,
  systemProvenance,
} from "./degradeStatus";
import type { ModelTrace } from "./types";

const L3_STATUS = "规则引擎回退，未完成真实 LLM 验证";

function trace(
  partial: Pick<ModelTrace, "provider" | "model" | "status"> &
    Partial<Pick<ModelTrace, "task" | "category">>,
): ModelTrace {
  return {
    category: partial.category ?? "llm",
    provider: partial.provider,
    model: partial.model,
    task: partial.task ?? "compliance_reasoning",
    latency_ms: 1,
    status: partial.status,
  };
}

describe("degrade level is taken only from an exact wire token", () => {
  it("accepts L0–L3 and nothing lookalike", () => {
    for (const level of ["L0", "L1", "L2", "L3"] as const) {
      expect(readLevel(level)).toEqual({ kind: "known", level });
    }
    expect(readLevel(undefined)).toEqual({ kind: "missing" });
    expect(readLevel(null)).toEqual({ kind: "missing" });
    expect(readLevel("")).toEqual({ kind: "missing" });
    expect(readLevel("  ")).toEqual({ kind: "missing" });
    expect(readLevel(" L0 ")).toEqual({ kind: "unrecognized" });
    expect(readLevel("l0")).toEqual({ kind: "unrecognized" });
    expect(readLevel("L9")).toEqual({ kind: "unrecognized" });
  });
});

describe("extraction, review, chat, and system health stay independent", () => {
  it("does not treat field source or a sibling level as extraction evidence", () => {
    const view = recordProvenance("extraction", {
      fields: [{ source: "llm", value: "INV-1" }],
    } as { degrade_level?: unknown });
    expect(view.capability).toBe("extraction");
    expect(view.level).toEqual({ kind: "missing" });
    expect(view.limits).toEqual(["unconfirmed"]);
    expect(view.llmVerified).toBe("absent");
    expect(view.serverStatus).toBeNull();
    expect(view.source).toEqual({ kind: "none" });
    expect(view.positioning).toBe(false);
  });

  it("keeps a rules extraction beside a cloud review and a traced chat", () => {
    const extraction = recordProvenance("extraction", {
      degrade_level: "L3",
      degrade_status: L3_STATUS,
      llm_verified: false,
      models: [trace({ provider: "deepseek", model: "deepseek-chat", status: "failed", task: "field_extraction" })],
    });
    const review = recordProvenance("review", {
      degrade_level: "L0",
      degrade_status: "正常：真实模型链路可用",
      llm_verified: true,
      models: [trace({ provider: "deepseek", model: "deepseek-chat", status: "ok" })],
    });
    const chat = chatProvenance({
      role: "assistant",
      blocked: false,
      models: [trace({ provider: "deepseek", model: "deepseek-chat", status: "ok", task: "chat" })],
      degrade_level: "L0",
      llm_verified: true,
    });
    expect(extraction.level).toEqual({ kind: "known", level: "L3" });
    expect(extraction.limits).toEqual(["L3"]);
    expect(extraction.serverStatus).toBe(L3_STATUS);
    expect(extraction.llmVerified).toBe(false);
    expect(review.level).toEqual({ kind: "known", level: "L0" });
    expect(review.limits).toEqual(["L0"]);
    expect(review.source).toMatchObject({ provider: "deepseek", model: "deepseek-chat", status: "ok" });
    expect(chat?.level).toEqual({ kind: "missing" });
    expect(chat?.limits).toEqual(["unconfirmed"]);
    expect(chat?.llmVerified).toBe("absent");
    expect(chat?.serverStatus).toBeNull();
    expect(chat?.source).toMatchObject({ provider: "deepseek", status: "ok" });
    expect(chat?.positioning).toBe(false);
  });

  it("does not copy current L0 health onto a stored L3 report", () => {
    const health = systemProvenance({
      degrade_level: "L0",
      llm_provider_chain: ["deepseek", "qwen", "ollama"],
      models: [
        {
          category: "llm",
          provider: "deepseek",
          model: "deepseek-chat",
          deployment: "cloud",
          stage: "reasoning",
          healthy: true,
        },
        {
          category: "llm",
          provider: "ollama",
          model: "qwen2.5:7b",
          deployment: "local",
          stage: "reasoning",
          healthy: false,
        },
      ],
    });
    const report = recordProvenance("review", {
      degrade_level: "L3",
      degrade_status: L3_STATUS,
      llm_verified: false,
    });
    expect(health.scope).toBe("system");
    expect(health.level).toEqual({ kind: "known", level: "L0" });
    expect(health.source).toMatchObject({
      kind: "health",
      provider: "deepseek",
      model: "deepseek-chat",
      deployment: "cloud",
      local: false,
    });
    expect(health.localCaveat).toBe(false);
    expect(health.chain).toEqual(["deepseek", "qwen", "ollama"]);
    expect(health.positioning).toBe(true);
    expect(report.level).toEqual({ kind: "known", level: "L3" });
    expect(report.serverStatus).toBe(L3_STATUS);
    expect(report.positioning).toBe(false);
    expect(report.chain).toBeNull();
  });

  it("renders L2 only from an L2 field, and names qwen only from that payload", () => {
    const health = systemProvenance({
      degrade_level: "L2",
      models: [
        {
          category: "llm",
          provider: "ollama",
          model: "qwen2.5:7b",
          deployment: "local",
          stage: "reasoning",
          healthy: true,
        },
      ],
    });
    const missingLevel = systemProvenance({
      models: [
        {
          category: "llm",
          provider: "ollama",
          model: "qwen2.5:7b",
          deployment: "local",
          stage: "reasoning",
          healthy: true,
        },
      ],
    });
    const chat = chatProvenance({
      role: "assistant",
      models: [trace({ provider: "ollama", model: "qwen2.5:7b", status: "ok", task: "chat" })],
    });
    expect(health.level).toEqual({ kind: "known", level: "L2" });
    expect(health.limits).toEqual(["L2"]);
    expect(health.source).toMatchObject({ model: "qwen2.5:7b", local: true });
    expect(health.localCaveat).toBe(true);
    expect(missingLevel.level).toEqual({ kind: "missing" });
    expect(missingLevel.limits).toEqual(["unconfirmed"]);
    expect(missingLevel.limits).not.toContain("L2");
    expect(chat?.level.kind).toBe("missing");
    expect(chat?.limits).toEqual(["unconfirmed"]);
    expect(chat?.source).toMatchObject({ model: "qwen2.5:7b", local: true });
    expect(chat?.localCaveat).toBe(true);
  });

  it("flags a cloud trace on an L2 record without rewriting the level", () => {
    const view = recordProvenance("review", {
      degrade_level: "L2",
      degrade_status: "SERVER STATUS L2",
      llm_verified: true,
      models: [trace({ provider: "deepseek", model: "deepseek-chat", status: "ok" })],
    });
    expect(view.level).toEqual({ kind: "known", level: "L2" });
    expect(view.limits).toEqual(["L2", "inconsistent"]);
    expect(view.localCaveat).toBe(false);
  });

  it("keeps L1 as backup cloud and does not promote a string boolean", () => {
    const view = recordProvenance("review", {
      degrade_level: "L1",
      degrade_status: "已切换备用云端模型",
      llm_verified: "true",
      models: [trace({ provider: "qwen", model: "qwen-plus", status: "fallback" })],
    });
    expect(view.level).toEqual({ kind: "known", level: "L1" });
    expect(view.limits).toEqual(["L1"]);
    expect(view.llmVerified).toBe("absent");
    expect(view.source).toMatchObject({ provider: "qwen", model: "qwen-plus", status: "fallback", local: false });
  });

  it("shows an L3 model trace as a disagreement, not as success", () => {
    const agreed = recordProvenance("extraction", {
      degrade_level: "L3",
      degrade_status: L3_STATUS,
      llm_verified: false,
      models: [trace({ provider: "deepseek", model: "deepseek-chat", status: "failed", task: "field_extraction" })],
    });
    const disagreed = recordProvenance("review", {
      degrade_level: "L3",
      degrade_status: L3_STATUS,
      llm_verified: false,
      models: [trace({ provider: "deepseek", model: "deepseek-chat", status: "ok" })],
    });
    expect(agreed.limits).toEqual(["L3"]);
    expect(agreed.source).toMatchObject({ status: "failed" });
    expect(disagreed.limits).toEqual(["L3", "inconsistent"]);
  });

  it("ignores OCR traces, unhealthy rows, and a non-boolean healthy flag", () => {
    const view = systemProvenance({
      degrade_level: "L3",
      models: [
        { category: "ocr", provider: "local", model: "rapidocr", deployment: "local", healthy: true },
        { category: "llm", provider: "deepseek", model: "deepseek-chat", deployment: "cloud", healthy: "true" },
      ],
    });
    expect(view.source).toEqual({ kind: "none" });
    expect(view.limits).toEqual(["L3"]);
  });

  it("drops a provider chain that is not a list of names", () => {
    expect(systemProvenance({ degrade_level: "L0", llm_provider_chain: ["deepseek", ""] }).chain).toBeNull();
    expect(systemProvenance({ degrade_level: "L0" }).chain).toBeNull();
  });

  it("skips user turns and blocked assistant turns do not become L3", () => {
    expect(chatProvenance({ role: "user", models: [] })).toBeNull();
    const blocked = chatProvenance({ role: "assistant", blocked: true });
    expect(blocked?.blocked).toBe(true);
    expect(blocked?.limits).toEqual(["unconfirmed"]);
    expect(blocked?.level).toEqual({ kind: "missing" });
  });
});
