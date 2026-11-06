import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorText, retryAfterSeconds } from "../api/errors";

function is429(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const problem = (error as { problem?: { status?: number } }).problem;
  return problem?.status === 429;
}

/** Shows 429 with a live countdown. Never auto-retries. */
export function RateLimitNotice({
  error,
  onExpire,
}: {
  error: unknown;
  onExpire?: () => void;
}) {
  const { t } = useTranslation();
  const initial = retryAfterSeconds(error) ?? 0;
  const [left, setLeft] = useState(initial);
  const hadCountdown = useRef(initial > 0);

  useEffect(() => {
    setLeft(initial);
    if (initial > 0) hadCountdown.current = true;
  }, [initial, error]);

  useEffect(() => {
    if (left <= 0) {
      // Only notify expiry after a real countdown finished — never clear on mount when Retry-After was missing.
      if (hadCountdown.current) onExpire?.();
      return;
    }
    const id = window.setTimeout(() => setLeft((v) => v - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left, onExpire]);

  if (!is429(error)) return null;

  return (
    <div className="banner error-notice audit-rate-limit" role="alert">
      <strong>{t("audit.rateLimitedTitle")}</strong>
      <div>{errorText(error)}</div>
      {left > 0 ? (
        <div className="audit-countdown tabular-nums" aria-live="polite">
          {t("audit.countdown", { seconds: left })}
        </div>
      ) : (
        <div className="audit-countdown" role="status">
          {t("errors.RATE_LIMITED")}
        </div>
      )}
    </div>
  );
}
