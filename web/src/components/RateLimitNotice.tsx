import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorText, retryAfterSeconds } from "../api/errors";
import { remainingSeconds, useClock } from "../hooks/useClock";

function is429(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const problem = (error as { problem?: { status?: number } }).problem;
  return problem?.status === 429;
}

/**
 * 429 banner with live countdown. Parent should remount with a new key when the
 * underlying rate-limit error changes so the deadline re-initializes cleanly.
 */
export function RateLimitNotice({
  error,
  onExpire,
}: {
  error: unknown;
  onExpire?: () => void;
}) {
  const { t } = useTranslation();
  const seconds = retryAfterSeconds(error) ?? 0;
  const [deadline] = useState(() =>
    seconds > 0 ? Date.now() + seconds * 1000 : null,
  );
  const now = useClock(Boolean(deadline));
  const left = remainingSeconds(deadline, now);
  const expiredRef = useRef(false);

  useEffect(() => {
    if (!deadline || left > 0 || expiredRef.current) return;
    expiredRef.current = true;
    onExpire?.();
  }, [deadline, left, onExpire]);

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
