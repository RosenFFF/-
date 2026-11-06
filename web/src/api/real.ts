import { body, http, json, ApiError, aborted } from "./http";
import { wait } from "./poll";
import type { Api, ChatEvent, Language } from "./types";

const id = encodeURIComponent;

const TERMINAL = new Set(["done", "error"]);

/** SSE framing survives split UTF-8/chunks, CRLF, comments and multiple data lines. */
export async function* readEvents(
  response: Response,
): AsyncGenerator<ChatEvent> {
  if (!response.body)
    throw new ApiError({ status: 0, code: "STREAM_INTERRUPTED" });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
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
        const eventId = lines
          .find((l) => l.startsWith("id:"))
          ?.slice(3)
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
            parsed = {
              event,
              data: JSON.parse(data),
              ...(eventId ? { id: eventId } : {}),
            } as ChatEvent;
          } catch {
            throw new ApiError({ status: 0, code: "STREAM_INTERRUPTED" });
          }
          if (TERMINAL.has(event)) finished = true;
          yield parsed;
        }
      }
      if (chunk.done || finished) break;
    }
    if (!finished) throw new ApiError({ status: 0, code: "STREAM_INTERRUPTED" });
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

async function postChatStream(
  reviewId: string,
  content: string,
  language: Language,
  signal: AbortSignal | undefined,
  lastEventId: string | undefined,
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (lastEventId) headers["Last-Event-ID"] = lastEventId;
  return http(`/reviews/${id(reviewId)}/messages`, {
    method: "POST",
    ...body({ content, language }),
    headers,
    signal,
  });
}

function isInterrupt(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    ["STREAM_INTERRUPTED", "NETWORK_ERROR"].includes(error.problem.code)
  );
}

/**
 * Start or resume an SSE chat stream. On drop, re-POST with Last-Event-ID
 * (same content/language) and skip already-seen event ids. Never fabricates
 * a success stream. Resume 404 → stop (caller should load history, not resend).
 */
export type AskStreamOptions = {
  signal?: AbortSignal;
  lastEventId?: string;
  onResume?: (attempt: number) => void;
};

export async function* askStream(
  reviewId: string,
  content: string,
  language: Language,
  options: AskStreamOptions = {},
): AsyncGenerator<ChatEvent> {
  const { signal, onResume } = options;
  let lastEventId = options.lastEventId;
  let streamId: string | undefined =
    options.lastEventId?.includes(":") === true
      ? options.lastEventId.slice(0, options.lastEventId.lastIndexOf(":"))
      : undefined;
  const seen = new Set<string>();
  let attempts = 0;
  while (true) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    try {
      const resume = lastEventId ?? (streamId ? `${streamId}:0` : undefined);
      const response = await postChatStream(
        reviewId,
        content,
        language,
        signal,
        resume,
      );
      const headerStream = response.headers.get("X-Chat-Stream-ID");
      if (headerStream) streamId = headerStream;
      const type = response.headers.get("Content-Type") ?? "";
      if (!type.includes("text/event-stream")) {
        // JSON one-shot (e.g. blocked) — not a fabricated SSE success path.
        const message = await response.json();
        yield { event: "done", data: message };
        return;
      }
      for await (const event of readEvents(response)) {
        if (event.id) {
          if (seen.has(event.id)) continue;
          seen.add(event.id);
          lastEventId = event.id;
        }
        yield event;
        if (TERMINAL.has(event.event)) return;
      }
      return;
    } catch (error) {
      if (aborted(error)) throw error;
      // HTTP 503 JSON (Accept mismatch edge) or explicit MODEL_UNAVAILABLE — no resume inventing success.
      if (
        error instanceof ApiError &&
        (error.problem.code === "MODEL_UNAVAILABLE" ||
          error.problem.status === 503)
      )
        throw error;
      // Expired/foreign stream: do not invent a new question POST.
      if (
        error instanceof ApiError &&
        (error.problem.status === 404 || error.problem.code === "NOT_FOUND")
      )
        throw error;
      if (!isInterrupt(error) || attempts >= 3) throw error;
      attempts += 1;
      onResume?.(attempts);
      await wait(1000 * 2 ** (attempts - 1), signal);
    }
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
  ask: (reviewId, content, language, signal, lastEventId) =>
    askStream(reviewId, content, language, { signal, lastEventId }),
  audit: (reviewId) =>
    json(reviewId ? `/reviews/${id(reviewId)}/audit` : "/audit/logs"),
  verifyAudit: () => json("/audit/verify"),
  models: (signal) => json("/system/models", { signal }),
};
