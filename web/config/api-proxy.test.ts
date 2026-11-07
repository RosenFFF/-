import { describe, expect, it } from "vitest";
import { resolveApiProxyTarget } from "./api-proxy.ts";

describe("server-side API proxy target", () => {
  it("keeps the existing default", () => {
    expect(resolveApiProxyTarget(undefined)).toBe("http://127.0.0.1:8000");
  });
  it.each([
    ["http://127.0.0.1:8002", "http://127.0.0.1:8002"],
    ["https://localhost:8443/", "https://localhost:8443"],
    ["http://[::1]:8002", "http://[::1]:8002"],
  ])("accepts loopback origin %s", (input, expected) => {
    expect(resolveApiProxyTarget(input)).toBe(expected);
  });
  it.each([
    "", "not-a-url", " http://127.0.0.1:8002", "http://127.0.0.1:8002 ",
    "ftp://localhost:8002", "https://example.com", "http://0.0.0.0:8002",
    "http://localhost.example.com:8002", "http://127.0.0.1:8002/api",
    "http://127.0.0.1:8002?key=example", "http://127.0.0.1:8002#example",
    "http://example:example@localhost:8002",
  ])("rejects invalid or non-loopback targets without echoing input", (input) => {
    expect(() => resolveApiProxyTarget(input)).toThrow("ST143_API_PROXY_TARGET must be");
    try { resolveApiProxyTarget(input); } catch (error) {
      expect(String(error)).not.toContain("key=example");
      expect(String(error)).not.toContain("example:example");
    }
  });
});
