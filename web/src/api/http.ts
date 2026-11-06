import type { Problem } from "./types";

export class ApiError extends Error {
  problem: Problem;
  constructor(problem: Problem) {
    super(problem.code);
    this.name = "ApiError";
    this.problem = problem;
  }
}
export const aborted = (error: unknown) =>
  error instanceof Error && error.name === "AbortError";
export function csrfCookie(
  cookie = typeof document === "undefined" ? "" : document.cookie,
): string {
  const value = cookie
    .split(";")
    .map((v) => v.trim())
    .find((v) => v.startsWith("csrf_token="));
  try {
    return value ? decodeURIComponent(value.slice("csrf_token=".length)) : "";
  } catch {
    return "";
  }
}
let refresh: Promise<void> | null = null;
export function expireSession() {
  if (typeof window !== "undefined")
    window.dispatchEvent(new Event("session-expired"));
}
/** Only same-origin /api/v1 paths: credentials/CSRF must never leak to arbitrary URLs. */
export async function http(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes(".."))
    throw new ApiError({ status: 0, code: "INTERNAL_ERROR" });
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (
    ["POST", "PUT", "PATCH", "DELETE"].includes(method) &&
    path !== "/auth/login"
  ) {
    // Re-read on every request/retry: refreshing rotates this cookie.
    const csrf = csrfCookie();
    if (csrf) headers.set("X-CSRF-Token", csrf);
    else headers.delete("X-CSRF-Token");
  }
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      method,
      headers,
      credentials: "include",
      cache: "no-store",
    });
  } catch (error) {
    if (aborted(error)) throw error;
    throw new ApiError({ status: 0, code: "NETWORK_ERROR" });
  }
  if (
    response.status === 401 &&
    retry &&
    (!path.startsWith("/auth/") || path === "/auth/me")
  ) {
    // One refresh for parallel 401s. Retry only after an auth rejection, never after network failure.
    refresh ??= http("/auth/refresh", { method: "POST" }, false)
      .then(() => undefined)
      .finally(() => {
        refresh = null;
      });
    await refresh;
    return http(path, init, false);
  }
  if (!response.ok) {
    let problem: Partial<Problem> = {};
    try {
      const parsed: unknown = await response.json();
      if (parsed && typeof parsed === "object")
        problem = parsed as Partial<Problem>;
    } catch {
      /* Proxies may return HTML; never show it. */
    }
    if (response.status === 401 && path !== "/auth/login") expireSession();
    const retryHeader =
      response.headers.get("Retry-After") ??
      response.headers.get("retry-after");
    const retryParsed = retryHeader ? Number.parseInt(retryHeader, 10) : NaN;
    let retry_after =
      Number.isFinite(retryParsed) && retryParsed > 0 ? retryParsed : undefined;
    // 429 without Retry-After still surfaces a short countdown so the UI never auto-hammers.
    if (response.status === 429 && retry_after === undefined) retry_after = 1;
    const code =
      response.status === 501
        ? "NOT_IMPLEMENTED"
        : response.status === 429
          ? (problem.code ?? "RATE_LIMITED")
          : response.status === 503 && problem.code === "RATE_LIMIT_UNAVAILABLE"
            ? "RATE_LIMIT_UNAVAILABLE"
            : (problem.code ??
              (response.status === 404 ? "NOT_FOUND" : "INTERNAL_ERROR"));
    // Never auto-retry 429/503 — callers show Retry-After countdown or unavailable state.
    throw new ApiError({
      status: response.status,
      code,
      request_id:
        problem.request_id || response.headers.get("X-Request-ID") || undefined,
      retry_after,
    });
  }
  return response;
}
export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await http(path, init)).json() as Promise<T>;
}
export function body(value: unknown): RequestInit {
  return {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  };
}
