import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.doUnmock("../mock/api");
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});
describe("real mode is never replaced by mock on errors", () => {
  it.each([400, 401, 403, 404, 409, 422, 429, 500, 501, 503])(
    "HTTP %i rejects with no mock load or fallback",
    async (status) => {
      vi.resetModules();
      vi.stubEnv("VITE_USE_MOCK", "false");
      const mockLoaded = vi.fn();
      vi.doMock("../mock/api", () => {
        mockLoaded();
        return { mockApi: {} };
      });
      const fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "MODEL_UNAVAILABLE",
            status,
            request_id: "test-request",
          }),
          { status },
        ),
      );
      vi.stubGlobal("fetch", fetch);
      const { api, useMock } = await import("./index");
      const { realApi } = await import("./real");
      expect(useMock).toBe(false);
      expect(api).toBe(realApi);
      await expect(
        api.startReview({
          document_ids: ["fixture"],
          destination_country: "RU",
          language: "zh-CN",
        }),
      ).rejects.toMatchObject({
        problem: {
          status,
          code: status === 501 ? "NOT_IMPLEMENTED" : "MODEL_UNAVAILABLE",
        },
      });
      expect(fetch).toHaveBeenCalledTimes(status === 401 ? 2 : 1);
      expect(mockLoaded).not.toHaveBeenCalled();
    },
  );
  it("network failure does not load mock or retry the POST", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_USE_MOCK", "false");
    const mockLoaded = vi.fn();
    vi.doMock("../mock/api", () => {
      mockLoaded();
      return { mockApi: {} };
    });
    const fetch = vi.fn().mockRejectedValue(new TypeError("network failed"));
    vi.stubGlobal("fetch", fetch);
    const { api } = await import("./index");
    await expect(
      api.startReview({
        document_ids: ["fixture"],
        destination_country: "RU",
        language: "en",
      }),
    ).rejects.toMatchObject({ problem: { code: "NETWORK_ERROR" } });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(mockLoaded).not.toHaveBeenCalled();
  });
  it("an unset flag defaults to real mode", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_USE_MOCK", undefined);
    const { useMock, api } = await import("./index");
    const { realApi } = await import("./real");
    expect(useMock).toBe(false);
    expect(api).toBe(realApi);
  });
  it("production ignores an explicitly true mock flag", async () => {
    vi.resetModules();
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_USE_MOCK", "true");
    const mockLoaded = vi.fn();
    vi.doMock("../mock/api", () => {
      mockLoaded();
      return { mockApi: {} };
    });
    const { useMock, api } = await import("./index");
    const { realApi } = await import("./real");
    expect(useMock).toBe(false);
    expect(api).toBe(realApi);
    expect(mockLoaded).not.toHaveBeenCalled();
  });
  it.each(["history", "translation", "ask"])(
    "%s 501 never yields a mock response",
    async (surface) => {
      vi.resetModules();
      vi.stubEnv("VITE_USE_MOCK", "false");
      const mockLoaded = vi.fn();
      vi.doMock("../mock/api", () => {
        mockLoaded();
        return { mockApi: {} };
      });
      const fetch = vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ code: "MODEL_UNAVAILABLE", status: 501 }),
            { status: 501 },
          ),
        );
      vi.stubGlobal("fetch", fetch);
      const { api } = await import("./index");
      const events: unknown[] = [];
      const result =
        surface === "history"
          ? api.messages("fixture")
          : surface === "translation"
            ? api.review("fixture", "vi")
            : (async () => {
                for await (const event of api.ask("fixture", "question", "vi"))
                  events.push(event);
              })();
      await expect(result).rejects.toMatchObject({
        problem: { status: 501, code: "NOT_IMPLEMENTED" },
      });
      expect(events).toEqual([]);
      expect(mockLoaded).not.toHaveBeenCalled();
      expect(fetch).toHaveBeenCalledTimes(1);
    },
  );
});
