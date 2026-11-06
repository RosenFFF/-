import { ApiError } from "./http";

export function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
/** Bounded polling, cancellable on navigation. Never interpret a failed job as success. */
export async function poll<
  T extends {
    status: string;
    error?: { code: string; status: number; request_id?: string } | null;
  },
>(
  load: () => Promise<T>,
  terminal: string,
  signal?: AbortSignal,
  onProgress?: (value: T) => void,
  interval = 1000,
  attempts = 180,
): Promise<T> {
  for (let i = 0; i < attempts; i++) {
    signal?.throwIfAborted();
    const result = await load();
    onProgress?.(result);
    if (result.status === terminal) return result;
    if (result.status === "failed")
      throw new ApiError(
        result.error ?? { status: 503, code: "MODEL_UNAVAILABLE" },
      );
    await wait(interval, signal);
  }
  throw new ApiError({ status: 408, code: "PROCESSING_TIMEOUT" });
}
