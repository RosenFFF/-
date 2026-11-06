import i18n from "../i18n";
import { ApiError } from "./http";
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
  "QUOTA_EXCEEDED",
  "MODEL_UNAVAILABLE",
  "INTERNAL_ERROR",
  "NETWORK_ERROR",
  "PROCESSING_TIMEOUT",
  "STREAM_INTERRUPTED",
] as const;
export function errorText(error: unknown): string {
  const problem =
    error instanceof ApiError
      ? error.problem
      : { code: "INTERNAL_ERROR", request_id: undefined };
  const code = errorCodes.includes(problem.code as (typeof errorCodes)[number])
    ? problem.code
    : "INTERNAL_ERROR";
  const text = i18n.t(`errors.${code}`);
  return problem.request_id
    ? `${text} (${i18n.t("common.requestId")}: ${problem.request_id})`
    : text;
}
