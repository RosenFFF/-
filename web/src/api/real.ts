import { body, http, json, ApiError } from "./http";
import type { Api, ChatEvent } from "./types";

const id = encodeURIComponent;
/** SSE framing survives split UTF-8/chunks, CRLF, comments and multiple data lines. */
export async function* readEvents(
  response: Response,
): AsyncGenerator<ChatEvent> {
  if (!response.body)
    throw new ApiError({ status: 0, code: "STREAM_INTERRUPTED" });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;
  try {
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const lines = frame.split("\n");
        const event = lines
          .find((l) => l.startsWith("event:"))
          ?.slice(6)
          .trim();
        const data = lines
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (
          event &&
          ["delta", "citation", "done", "error"].includes(event) &&
          data
        ) {
          let parsed: ChatEvent;
          try {
            parsed = { event, data: JSON.parse(data) } as ChatEvent;
          } catch {
            throw new ApiError({ status: 0, code: "STREAM_INTERRUPTED" });
          }
          if (event === "done" || event === "error") done = true;
          yield parsed;
        }
      }
      if (chunk.done || done) break;
    }
    if (!done) throw new ApiError({ status: 0, code: "STREAM_INTERRUPTED" });
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
export const realApi: Api = {
  login: (username, password) =>
    json("/auth/login", { method: "POST", ...body({ username, password }) }),
  me: (signal) => json("/auth/me", { signal }),
  logout: async () => {
    await http("/auth/logout", { method: "POST" });
  },
  listDocuments: (signal) => json("/documents?page_size=100", { signal }),
  upload: (file, docType, signal) => {
    const form = new FormData();
    form.set("file", file);
    form.set("doc_type", docType);
    return json("/documents", { method: "POST", body: form, signal });
  },
  document: (documentId, signal) =>
    json(`/documents/${id(documentId)}`, { signal }),
  recognition: (documentId, signal) =>
    json(`/documents/${id(documentId)}/recognition`, { signal }),
  image: async (documentId, page, signal) =>
    (
      await http(`/documents/${id(documentId)}/pages/${page}/image`, { signal })
    ).blob(),
  patchFields: (documentId, version, fields) =>
    json(`/documents/${id(documentId)}/fields`, {
      method: "PATCH",
      ...body({ version, fields }),
    }),
  startReview: (input, signal) =>
    json("/reviews", { method: "POST", ...body(input), signal }),
  review: (reviewId, language, signal) =>
    json(`/reviews/${id(reviewId)}?language=${id(language)}`, { signal }),
  rule: (ruleId, signal) => json(`/rules/${id(ruleId)}`, { signal }),
  messages: (reviewId, signal) =>
    json(`/reviews/${id(reviewId)}/messages`, { signal }),
  async *ask(reviewId, content, language, signal) {
    const response = await http(`/reviews/${id(reviewId)}/messages`, {
      method: "POST",
      ...body({ content, language }),
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      signal,
    });
    if (!response.headers.get("Content-Type")?.includes("text/event-stream")) {
      yield { event: "done", data: await response.json() };
      return;
    }
    yield* readEvents(response);
  },
  audit: (reviewId) =>
    json(reviewId ? `/reviews/${id(reviewId)}/audit` : "/audit/logs"),
  verifyAudit: () => json("/audit/verify"),
  models: (signal) => json("/system/models", { signal }),
};
