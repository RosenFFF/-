import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { body, csrfCookie, http, ApiError } from "./http";
import { realApi, readEvents } from "./real";
import { poll } from "./poll";
const ok = (data: unknown = {}) =>
  new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
const fail = (status: number, code: string) =>
  new Response(JSON.stringify({ status, code, request_id: "request-123" }), {
    status,
  });
beforeEach(() =>
  vi.stubGlobal("document", { cookie: "other=x; csrf_token=signed%2Bcsrf" }),
);
afterEach(() => vi.unstubAllGlobals());
describe("same-origin cookie transport", () => {
  it("reads only csrf_token and safely handles corrupt encoding", () => {
    expect(
      csrfCookie("access_token=no; csrf_token=a%2Bb; refresh_token=no"),
    ).toBe("a+b");
    expect(csrfCookie("csrf_token=%no")).toBe("");
    expect(csrfCookie("other=x")).toBe("");
  });
  it.each(["POST", "PUT", "PATCH", "DELETE"])(
    "%s sends readable CSRF and includes HttpOnly credentials",
    async (method) => {
      const fetch = vi.fn().mockResolvedValue(ok());
      vi.stubGlobal("fetch", fetch);
      await http("/documents", { method, ...body({}) });
      const [url, init] = fetch.mock.calls[0];
      expect(url).toBe("/api/v1/documents");
      expect(init.credentials).toBe("include");
      expect(init.cache).toBe("no-store");
      expect(init.headers.get("X-CSRF-Token")).toBe("signed+csrf");
      expect(init.headers.has("Authorization")).toBe(false);
    },
  );
  it("GET and login do not send CSRF but still include credentials", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(ok()));
    vi.stubGlobal("fetch", fetch);
    await http("/documents");
    await realApi.login("reviewer", "fixture-only");
    for (const [, init] of fetch.mock.calls) {
      expect(init.credentials).toBe("include");
      expect(init.headers.has("X-CSRF-Token")).toBe(false);
    }
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      username: "reviewer",
      password: "fixture-only",
    });
  });
  it("uploads actual file+doc_type without setting multipart boundary manually", async () => {
    const fetch = vi.fn().mockResolvedValue(ok({ id: "document" }));
    vi.stubGlobal("fetch", fetch);
    const file = new File(["image"], "sample.png", { type: "image/png" });
    await realApi.upload(file, "certificate_of_origin");
    const [, init] = fetch.mock.calls[0];
    expect(init.body.get("file").name).toBe("sample.png");
    expect(init.body.get("doc_type")).toBe("certificate_of_origin");
    expect(init.headers.has("Content-Type")).toBe(false);
  });
  it("uses one refresh for parallel 401s and rereads rotated CSRF", async () => {
    const fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/auth/refresh")) {
        vi.stubGlobal("document", { cookie: "csrf_token=rotated" });
        return ok();
      }
      const count = fetch.mock.calls.filter(([u]) => u === url).length;
      return count === 1 ? fail(401, "AUTH_TOKEN_EXPIRED") : ok();
    });
    vi.stubGlobal("fetch", fetch);
    await Promise.all([
      http("/documents/one", { method: "PATCH" }),
      http("/documents/two", { method: "PATCH" }),
    ]);
    expect(
      fetch.mock.calls.filter(([url]) => url.endsWith("/auth/refresh")),
    ).toHaveLength(1);
    expect(fetch.mock.calls.at(-1)?.[1].headers.get("X-CSRF-Token")).toBe(
      "rotated",
    );
  });
  it("does not replay a CSRF rejection or failed network write", async () => {
    const fetch = vi.fn().mockResolvedValue(fail(403, "CSRF_FAILED"));
    vi.stubGlobal("fetch", fetch);
    await expect(http("/documents", { method: "POST" })).rejects.toMatchObject({
      problem: { code: "CSRF_FAILED", request_id: "request-123" },
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    fetch.mockRejectedValue(new TypeError("network"));
    await expect(http("/documents", { method: "POST" })).rejects.toMatchObject({
      problem: { code: "NETWORK_ERROR" },
    });
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("never attempts refresh for invalid login credentials", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(fail(401, "AUTH_INVALID_CREDENTIALS"));
    vi.stubGlobal("fetch", fetch);
    await expect(
      realApi.login("reviewer", "fixture-only"),
    ).rejects.toMatchObject({
      problem: { code: "AUTH_INVALID_CREDENTIALS", status: 401 },
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("refresh failure ends session, no infinite retry", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    const fetch = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(fail(401, "AUTH_TOKEN_EXPIRED")),
      );
    vi.stubGlobal("fetch", fetch);
    await expect(http("/documents")).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(dispatchEvent).toHaveBeenCalledTimes(1);
  });
  it("keeps server HTML/stack traces out of errors and keeps request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<secret-stack>", {
          status: 502,
          headers: { "X-Request-ID": "proxy-123" },
        }),
      ),
    );
    await expect(http("/documents")).rejects.toMatchObject({
      message: "INTERNAL_ERROR",
      problem: { request_id: "proxy-123" },
    });
  });
  it("handles null proxy JSON without exposing raw content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("null", { status: 502 })),
    );
    await expect(http("/documents")).rejects.toMatchObject({
      problem: { code: "INTERNAL_ERROR", status: 502 },
    });
  });
  it("rejects external credential targets", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(http("//evil.example")).rejects.toBeInstanceOf(ApiError);
    expect(fetch).not.toHaveBeenCalled();
  });
});
describe("job polling and SSE", () => {
  it("waits through uploaded/running then returns ready", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce({ status: "uploaded" })
      .mockResolvedValueOnce({ status: "ocr_running" })
      .mockResolvedValue({ status: "ready" });
    expect((await poll(load, "ready", undefined, undefined, 0)).status).toBe(
      "ready",
    );
    expect(load).toHaveBeenCalledTimes(3);
  });
  it("fails for a failed job, timeout and cancellation", async () => {
    await expect(
      poll(
        async () => ({
          status: "failed",
          error: { code: "MODEL_UNAVAILABLE", status: 503 },
        }),
        "ready",
      ),
    ).rejects.toMatchObject({ problem: { code: "MODEL_UNAVAILABLE" } });
    await expect(
      poll(
        async () => ({ status: "uploaded" }),
        "ready",
        undefined,
        undefined,
        0,
        1,
      ),
    ).rejects.toMatchObject({ problem: { code: "PROCESSING_TIMEOUT" } });
    const c = new AbortController();
    c.abort();
    const load = vi.fn();
    await expect(poll(load, "ready", c.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(load).not.toHaveBeenCalled();
  });
  it("parses split UTF-8/CRLF frames and comments", async () => {
    const data =
      ': ping\r\nevent: delta\r\ndata: {"text":"你好"}\r\n\r\nevent: done\r\ndata: {"id":"answer","role":"assistant","content":"你好","blocked":false}\r\n\r\n';
    const bytes = new TextEncoder().encode(data);
    const stream = new ReadableStream({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    });
    const events = [];
    for await (const event of readEvents(new Response(stream)))
      events.push(event);
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ event: "delta", data: { text: "你好" } });
  });
  it("EOF without done is interruption, not success", async () => {
    await expect(
      (async () => {
        for await (const event of readEvents(
          new Response('event: delta\ndata: {"text":"partial"}\n\n'),
        ))
          void event;
      })(),
    ).rejects.toMatchObject({ problem: { code: "STREAM_INTERRUPTED" } });
  });
});
