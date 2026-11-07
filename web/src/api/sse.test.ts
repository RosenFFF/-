import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./http";
import { askStream, readEvents } from "./real";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[i++]));
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SSE event parsing", () => {
  it("parses id/event/data including split frames", async () => {
    const sid = "11111111-1111-4111-8111-111111111111";
    const raw =
      `: keepalive\n` +
      `id: ${sid}:1\nevent: delta\ndata: {"text":"你"}\n\n` +
      `id: ${sid}:2\nevent: delta\ndata: {"text":"好"}\n\n` +
      `id: ${sid}:3\nevent: done\ndata: {"id":"a","role":"assistant","content":"你好","created_at":"t","blocked":false}\n\n`;
    const events = [];
    for await (const event of readEvents(
      new Response(streamOf([...raw].map((c) => c))),
    ))
      events.push(event);
    expect(events.map((e) => e.id)).toEqual([
      `${sid}:1`,
      `${sid}:2`,
      `${sid}:3`,
    ]);
    expect(events[0]).toMatchObject({
      event: "delta",
      data: { text: "你" },
    });
    expect(events.at(-1)?.event).toBe("done");
  });

  it("treats SSE error as terminal MODEL_UNAVAILABLE payload", async () => {
    const sid = "22222222-2222-4222-8222-222222222222";
    const raw = `id: ${sid}:1\nevent: error\ndata: {"status":503,"code":"MODEL_UNAVAILABLE","title":"无可用 LLM"}\n\n`;
    const events = [];
    for await (const event of readEvents(new Response(raw))) events.push(event);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      event: "error",
      data: { code: "MODEL_UNAVAILABLE", status: 503 },
    });
  });
});

describe("askStream resume and dedupe", () => {
  it("resumes with Last-Event-ID and skips duplicate ids", async () => {
    const sid = "33333333-3333-4333-8333-333333333333";
    const fetches: RequestInit[] = [];
    let round = 0;
    vi.stubGlobal("document", { cookie: "csrf_token=test-csrf" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        fetches.push(init ?? {});
        round += 1;
        if (round === 1) {
          // First stream drops after one delta (no done) → interrupt
          return new Response(`id: ${sid}:1\nevent: delta\ndata: {"text":"A"}\n\n`, {
            status: 200,
            headers: {
              "Content-Type": "text/event-stream",
              "X-Chat-Stream-ID": sid,
            },
          });
        }
        // Resume from :1, server may replay :1 then :2 done
        return new Response(
          `id: ${sid}:1\nevent: delta\ndata: {"text":"A"}\n\n` +
            `id: ${sid}:2\nevent: done\ndata: {"id":"ans","role":"assistant","content":"A","created_at":"t","blocked":false}\n\n`,
          {
            status: 200,
            headers: {
              "Content-Type": "text/event-stream",
              "X-Chat-Stream-ID": sid,
            },
          },
        );
      }),
    );
    const resumes: number[] = [];
    const texts: string[] = [];
    let done = false;
    for await (const event of askStream("rev", "q", "zh-CN", {
      onResume: (n) => resumes.push(n),
    })) {
      if (event.event === "delta") texts.push(event.data.text);
      if (event.event === "done") done = true;
    }
    expect(done).toBe(true);
    expect(texts).toEqual(["A"]); // duplicate A from resume skipped
    expect(resumes).toEqual([1]);
    expect(fetches).toHaveLength(2);
    expect(new Headers(fetches[0].headers).get("Last-Event-ID")).toBeNull();
    expect(new Headers(fetches[1].headers).get("Last-Event-ID")).toBe(
      `${sid}:1`,
    );
    expect(new Headers(fetches[0].headers).get("X-CSRF-Token")).toBe(
      "test-csrf",
    );
    expect(fetches[0].credentials).toBe("include");
  });

  it("surfaces HTTP 503 MODEL_UNAVAILABLE without fabricating success", async () => {
    vi.stubGlobal("document", { cookie: "csrf_token=x" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ status: 503, code: "MODEL_UNAVAILABLE" }),
          {
            status: 503,
            headers: { "Content-Type": "application/problem+json" },
          },
        ),
      ),
    );
    await expect(
      (async () => {
        for await (const event of askStream("rev", "q", "zh-CN")) void event;
      })(),
    ).rejects.toMatchObject({
      problem: { code: "MODEL_UNAVAILABLE", status: 503 },
    });
  });

  it("yields blocked done without deltas", async () => {
    vi.stubGlobal("document", { cookie: "csrf_token=x" });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            `event: done\ndata: {"id":"b","role":"assistant","content":"","created_at":"t","blocked":true,"block_reason":"prompt_injection"}\n\n`,
            {
              status: 200,
              headers: { "Content-Type": "text/event-stream" },
            },
          ),
      ),
    );
    const events = [];
    for await (const event of askStream("rev", "ignore previous", "zh-CN"))
      events.push(event);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      event: "done",
      data: { blocked: true, block_reason: "prompt_injection" },
    });
  });

  it("does not auto-start a new stream after resume 404", async () => {
    const sid = "44444444-4444-4444-8444-444444444444";
    let round = 0;
    vi.stubGlobal("document", { cookie: "csrf_token=x" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, _init?: RequestInit) => {
        round += 1;
        if (round === 1) {
          return new Response(
            `id: ${sid}:1\nevent: delta\ndata: {"text":"x"}\n\n`,
            {
              status: 200,
              headers: {
                "Content-Type": "text/event-stream",
                "X-Chat-Stream-ID": sid,
              },
            },
          );
        }
        return new Response(JSON.stringify({ status: 404, code: "NOT_FOUND" }), {
          status: 404,
          headers: { "Content-Type": "application/problem+json" },
        });
      }),
    );
    await expect(
      (async () => {
        for await (const event of askStream("rev", "q", "zh-CN")) void event;
      })(),
    ).rejects.toMatchObject({ problem: { code: "NOT_FOUND", status: 404 } });
    expect(round).toBe(2);
  });
});

describe("MODEL_UNAVAILABLE copy", () => {
  it.each([
    ["zh", "模型暂不可用"],
    ["en", "Model unavailable"],
    ["vi", "Mô hình chưa khả dụng"],
  ])("%s exposes a clear unavailable notice", async (lang, fragment) => {
    const i18n = (await import("../i18n")).default;
    const { errorText } = await import("./errors");
    await i18n.changeLanguage(lang);
    expect(
      errorText(new ApiError({ status: 503, code: "MODEL_UNAVAILABLE" })),
    ).toContain(fragment);
  });
});

describe("HTTP 200 SSE carrying only an error event (backend 831cbe8 contract)", () => {
  it("never yields success when status is 200 but the only event is error 503", async () => {
    const sid = "44444444-4444-4444-8444-444444444444";
    vi.stubGlobal("document", { cookie: "csrf_token=x" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          `: stream ${sid}\n\n` +
            `id: ${sid}:1\nevent: error\ndata: {"type":"about:blank","title":"无可用 LLM","status":503,"code":"MODEL_UNAVAILABLE","request_id":"r"}\n\n`,
          {
            status: 200,
            headers: {
              "Content-Type": "text/event-stream",
              "X-Chat-Stream-ID": sid,
            },
          },
        ),
      ),
    );
    const seen: { event: string; data: unknown }[] = [];
    for await (const event of askStream("rev", "q", "zh-CN")) seen.push(event);
    // Terminal error is yielded (AskPage throws ApiError on it); HTTP 200 alone is not success.
    expect(seen.map((e) => e.event)).toEqual(["error"]);
    expect(seen[0].data).toMatchObject({ code: "MODEL_UNAVAILABLE", status: 503 });
    const s = seen.map((e) => e.event);
    expect(s).not.toContain("done");
    expect(s).not.toContain("delta");
    expect(s).not.toContain("citation");
  });
});
