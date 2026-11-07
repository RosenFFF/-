import { describe, expect, it } from "vitest";
import { safeHarEntry, safeRequestUrl, summarizeSse } from "./demo-evidence.ts";

describe("demo evidence", () => {
  it("removes URL credentials, query and fragment", () => {
    expect(safeRequestUrl("https://user:secret@localhost:5175/api/v1/reviews/r?token=secret#secret")).toBe("https://localhost:5175/api/v1/reviews/r");
  });
  it("never preserves data or blob URL payloads", () => {
    expect(safeRequestUrl("data:text/plain,secret")).toBe("about:blank");
    expect(safeRequestUrl("blob:https://localhost/private")).toBe("about:blank");
  });
  it("HAR is metadata-only even for authentication requests", () => {
    const entry = safeHarEntry("https://localhost/api/v1/auth/login?secret=x", "POST", 200, "application/json; charset=utf-8");
    expect(entry.request.headers).toEqual([]);
    expect(entry.request.cookies).toEqual([]);
    expect(entry.request).not.toHaveProperty("postData");
    expect(entry.response.content).not.toHaveProperty("text");
    expect(JSON.stringify(entry)).not.toContain("secret");
  });
  const done = 'event: done\ndata: {"role":"assistant","content":"合规建议","blocked":false}\n\n';
  it("accepts a completed nonblocked stream", () => {
    expect(summarizeSse('event: delta\ndata: {"text":"建议"}\n\n' + done).success).toBe(true);
    expect(summarizeSse(done.replace(/\n/g, "\r\n")).success).toBe(true);
  });
  it.each([
    'event: error\ndata: {"status":503,"code":"MODEL_UNAVAILABLE"}\n\n',
    'event: delta\ndata: {"text":"部分"}\n\n',
    'event: done\ndata: {"role":"assistant","content":"","blocked":false}\n\n',
    'event: done\ndata: {"role":"assistant","content":"拒绝","blocked":true}\n\n',
    'event: done\ndata: invalid\n\n',
    done + 'event: error\ndata: {}\n\n',
  ])("does not equate HTTP 200 or partial/blocked/error streams with success", (body) => {
    expect(summarizeSse(body).success).toBe(false);
  });
});
