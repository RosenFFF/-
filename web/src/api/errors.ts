import i18n from "../i18n";
import { ApiError } from "./http";
import type { Problem } from "./types";
export const errorCodes = [
  "AUTH_INVALID_CREDENTIALS",
  "AUTH_TOKEN_EXPIRED",
  "AUTH_LOCKED",
  "PERMISSION_DENIED",
  "CSRF_FAILED",
  "NOT_FOUND",
  "VALIDATION_FAILED",
  "FILE_TOO_LARGE",
  "FILE_TYPE_UNSUPPORTED",
  "DOCUMENT_NOT_READY",
  "VERSION_CONFLICT",
  "ALREADY_EXISTS",
  "RATE_LIMITED",
  "RATE_LIMIT_UNAVAILABLE",
  "QUOTA_EXCEEDED",
  "MODEL_UNAVAILABLE",
  "INTERNAL_ERROR",
  "NOT_IMPLEMENTED",
  "NETWORK_ERROR",
  "PROCESSING_TIMEOUT",
  "STREAM_INTERRUPTED",
] as const;
export function errorText(error: unknown): string {
  const problem: Partial<Problem> =
    error instanceof ApiError
      ? error.problem
      : { code: "INTERNAL_ERROR", status: undefined, request_id: undefined };
  const code =
    problem.status === 501
      ? "NOT_IMPLEMENTED"
      : errorCodes.includes(problem.code as (typeof errorCodes)[number])
        ? (problem.code as (typeof errorCodes)[number])
        : "INTERNAL_ERROR";
  let text = i18n.t(`errors.${code}`);
  if (
    code === "RATE_LIMITED" &&
    typeof problem.retry_after === "number" &&
    problem.retry_after > 0
  ) {
    text = `${text} ${i18n.t("errors.RATE_LIMITED.retry", { seconds: problem.retry_after })}`;
  }
  return problem.request_id
    ? `${text} (${i18n.t("common.requestId")}: ${problem.request_id})`
    : text;
}

/** Remaining seconds from an ApiError, or null. */
export function retryAfterSeconds(error: unknown): number | null {
  if (!error || typeof error !== "object" || !("problem" in error)) return null;
  const problem = (error as { problem?: { retry_after?: number } }).problem;
  const value = problem?.retry_after;
  return typeof value === "number" && value > 0 ? value : null;
}
