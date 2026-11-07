export function safeRequestUrl(value: string): string {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) return "about:blank";
  return `${url.origin}${url.pathname}`;
}

export function summarizeSse(body: string) {
  const events: string[] = [];
  let chars = 0;
  let done = false;
  let blocked = false;
  let malformed = false;
  for (const frame of body.replace(/\r\n/g, "\n").split("\n\n")) {
    const lines = frame.split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    if (!event) continue;
    events.push(event);
    const text = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
    try {
      const data = JSON.parse(text) as { text?: unknown; content?: unknown; blocked?: unknown; role?: unknown };
      if (event === "delta" && typeof data.text === "string") chars += data.text.length;
      if (event === "done") {
        done = data.role === "assistant" && typeof data.content === "string" && data.content.trim().length > 0;
        blocked = data.blocked !== false;
      }
    } catch { malformed = true; }
  }
  return { events, chars, done, blocked, malformed, success: done && !blocked && !malformed && !events.includes("error") && events.at(-1) === "done" };
}

// A deliberately metadata-only HAR: no request/response bodies, headers or cookies.
export function safeHarEntry(url: string, method: string, status: number, mimeType: string) {
  return {
    startedDateTime: new Date().toISOString(), time: 0,
    request: { method, url: safeRequestUrl(url), httpVersion: "HTTP/1.1", headers: [], queryString: [], cookies: [], headersSize: -1, bodySize: -1 },
    response: { status, statusText: "", httpVersion: "HTTP/1.1", headers: [], cookies: [], content: { size: 0, mimeType: mimeType.split(";")[0] }, redirectURL: "", headersSize: -1, bodySize: -1 },
    cache: {}, timings: { send: 0, wait: 0, receive: 0 },
    comment: "Sanitized metadata only; body, headers, cookies and query omitted. Timings not measured.",
  };
}
