import { createElement as h, Fragment } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import {
  chatProvenance,
  recordProvenance,
  systemProvenance,
} from "../api/degradeStatus";
import i18n from "../i18n";
import en from "../i18n/en.json";
import vi from "../i18n/vi.json";
import zh from "../i18n/zh.json";
import { DegradeStrip } from "./DegradeStrip";
import type { ModelTrace } from "../api/types";

const L3_STATUS = "规则引擎回退，未完成真实 LLM 验证";

function llm(provider: string, model: string, status: ModelTrace["status"], task = "chat"): ModelTrace {
  return { category: "llm", provider, model, task, latency_ms: 1, status };
}

function markup(view: NonNullable<ReturnType<typeof chatProvenance>>, live = false) {
  return renderToStaticMarkup(h(DegradeStrip, { view, live }));
}

afterEach(async () => {
  await i18n.changeLanguage("zh");
});

describe("degrade strip copy", () => {
  it("keeps zh, en, and vi keys aligned and does not advertise accepted offline operation", () => {
    const keys = Object.keys(zh).filter((key) => key.startsWith("degrade."));
    expect(keys.length).toBeGreaterThan(10);
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
    expect(Object.keys(zh).sort()).toEqual(Object.keys(vi).sort());
    for (const key of keys) {
      expect(en[key as keyof typeof en], key).toBeTruthy();
      expect(vi[key as keyof typeof vi], key).toBeTruthy();
      expect(en[key as keyof typeof en]).not.toBe(zh[key as keyof typeof zh]);
      expect(vi[key as keyof typeof vi]).not.toBe(zh[key as keyof typeof zh]);
    }
    expect(zh["degrade.limit.L0"]).toContain("云端模型");
    expect(zh["degrade.limit.L3"]).toContain("规则引擎");
    expect(zh["degrade.limit.L3"]).toContain("人工复核");
    expect(zh["degrade.limit.L2"]).toContain("不是已验收的离线能力");
    expect(zh["degrade.positioning"]).toContain("云端模型为主");
    expect(zh["degrade.positioning"]).toContain("规则引擎为回退");
    const banned = [/离线模式可用/, /可离线运行/, /offline ready/i, /validated offline/i];
    for (const table of [zh, en, vi]) {
      for (const key of keys) {
        const text = table[key as keyof typeof table];
        for (const pattern of banned) expect(text).not.toMatch(pattern);
      }
    }
  });

  it.each([
    ["zh", "云端模型", "规则引擎。须人工复核。", "未确认", "不是已验收的离线能力"],
    ["en", "Cloud model.", "Rules engine. Human review is required.", "Unconfirmed", "not an accepted offline capability"],
    ["vi", "Mô hình đám mây.", "Bộ quy tắc. Cần người rà soát.", "Chưa xác nhận", "không phải năng lực ngoại tuyến đã nghiệm thu"],
  ])("%s states L0, L3, missing, and the L2 limit without promoting it", async (lang, l0, l3, missing, l2) => {
    await i18n.changeLanguage(lang);
    const cloud = markup(
      recordProvenance("review", {
        degrade_level: "L0",
        degrade_status: "SERVER STATUS L0",
        llm_verified: true,
        models: [llm("deepseek", "deepseek-chat", "ok", "compliance_reasoning")],
      }),
    );
    const rules = markup(
      recordProvenance("extraction", {
        degrade_level: "L3",
        degrade_status: L3_STATUS,
        llm_verified: false,
      }),
    );
    const local = markup(
      systemProvenance({
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
      }),
      true,
    );
    const absent = markup(recordProvenance("review", {}));
    expect(cloud).toContain(l0);
    expect(cloud).toContain("SERVER STATUS L0");
    expect(cloud).toContain('data-capability="review"');
    expect(cloud).toContain('data-level="L0"');
    expect(cloud).not.toContain(l3);
    expect(rules).toContain(l3);
    expect(rules).toContain(L3_STATUS);
    expect(rules).toContain('data-capability="extraction"');
    expect(rules).toContain('data-level="L3"');
    expect(rules).not.toContain(l0);
    expect(local).toContain("qwen2.5:7b");
    expect(local).toContain(l2);
    expect(local).toContain('data-level="L2"');
    expect(local).toContain('data-capability="system"');
    expect(local).toContain('aria-live="polite"');
    expect(absent).toContain(missing);
    expect(absent).toContain('data-level="missing"');
    expect(absent).not.toContain('data-level="L0"');
    expect(absent).not.toContain('data-level="L3"');
  });

  it("shows a mixed run as four different strips", () => {
    const extraction = markup(
      recordProvenance("extraction", {
        degrade_level: "L3",
        degrade_status: L3_STATUS,
        llm_verified: false,
      }),
    );
    const review = markup(
      recordProvenance("review", {
        degrade_level: "L0",
        degrade_status: "正常：真实模型链路可用",
        llm_verified: true,
        models: [llm("deepseek", "deepseek-chat", "ok", "compliance_reasoning")],
      }),
    );
    const chat = markup(
      chatProvenance({
        role: "assistant",
        blocked: false,
        models: [llm("deepseek", "deepseek-chat", "ok")],
        degrade_level: "L0",
      })!,
    );
    const health = markup(
      systemProvenance({
        degrade_level: "L2",
        llm_provider_chain: ["deepseek", "qwen", "ollama"],
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
      }),
    );
    expect(extraction).toContain("本单证识别结果");
    expect(extraction).toContain(L3_STATUS);
    expect(extraction).not.toContain("正常：真实模型链路可用");
    expect(extraction).not.toContain("qwen2.5:7b");
    expect(review).toContain("本报告自带的降级字段");
    expect(review).toContain("正常：真实模型链路可用");
    expect(review).toContain("deepseek-chat");
    expect(review).not.toContain(L3_STATUS);
    expect(review).not.toContain("产品定位");
    expect(chat).toContain('data-level="missing"');
    expect(chat).toContain("deepseek-chat");
    expect(chat).toContain("不以系统健康或报告级别填补");
    expect(chat).toContain('aria-live="off"');
    expect(chat).not.toContain('data-level="L0"');
    expect(chat).not.toContain('data-level="L2"');
    expect(chat).not.toContain("本响应标注为 L2");
    expect(chat).not.toContain(L3_STATUS);
    expect(health).toContain("当前 /system/models");
    expect(health).toContain('data-level="L2"');
    expect(health).toContain("qwen2.5:7b");
    expect(health).toContain("不是已验收的离线能力");
    expect(health).toContain("产品定位");
    expect(health).toContain("deepseek → qwen → ollama");
    expect(health).not.toContain(L3_STATUS);
    const together = renderToStaticMarkup(
      h(
        Fragment,
        null,
        h("div", { id: "historical" }, h(DegradeStrip, {
          view: recordProvenance("review", {
            degrade_level: "L3",
            degrade_status: L3_STATUS,
            llm_verified: false,
          }),
        })),
        h("div", { id: "current" }, h(DegradeStrip, {
          view: systemProvenance({
            degrade_level: "L0",
            models: [
              {
                category: "llm",
                provider: "deepseek",
                model: "deepseek-chat",
                deployment: "cloud",
                stage: "reasoning",
                healthy: true,
              },
            ],
          }),
        })),
      ),
    );
    const [historical, current] = together.split('id="current"');
    expect(historical).toContain('data-level="L3"');
    expect(historical).toContain(L3_STATUS);
    expect(current).toContain('data-level="L0"');
    expect(current).not.toContain(L3_STATUS);
  });

  it("does not put the strip in the tab order or move focus", () => {
    const html = markup(
      recordProvenance("review", {
        degrade_level: "L1",
        degrade_status: "已切换备用云端模型",
        llm_verified: true,
        models: [llm("qwen", "qwen-plus", "fallback", "compliance_reasoning")],
      }),
      true,
    );
    expect(html).toContain("备用云端模型");
    expect(html).toContain("qwen-plus");
    expect(html).toContain('role="status"');
    expect(html).not.toContain("tabindex");
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<a ");
    const source = html;
    expect(source).not.toMatch(/focus\(/);
  });
});
