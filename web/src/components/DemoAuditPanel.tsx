import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/http";
import { demoAuditApi } from "../api/demo";
import { errorText, retryAfterSeconds } from "../api/errors";
import type { Verify } from "../api/types";
import { api } from "../api";

type Props = {
  busy: boolean;
  rateBlocked: boolean;
  onBusy: (busy: boolean) => void;
  onError: (error: unknown) => void;
  onVerify: (verify: Verify) => void;
  onStatsRefresh: () => Promise<void>;
  initialLogId?: string;
};

function statusOf(error: unknown): number {
  if (!error || typeof error !== "object" || !("problem" in error)) return 0;
  return Number((error as { problem?: { status?: number } }).problem?.status) || 0;
}

/** Isolated DEMO hash-chain drill. Must not ship in production bundles. */
export function DemoAuditPanel({
  busy,
  rateBlocked,
  onBusy,
  onError,
  onVerify,
  onStatsRefresh,
  initialLogId = "",
}: Props) {
  const { t } = useTranslation();
  const [demoLogId, setDemoLogId] = useState(initialLogId);
  const [demoMsg, setDemoMsg] = useState<string | null>(null);
  const [rateError, setRateError] = useState<unknown>(null);
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!rateError) {
      setLeft(0);
      return;
    }
    setLeft(retryAfterSeconds(rateError) ?? 1);
  }, [rateError]);

  useEffect(() => {
    if (left <= 0) return;
    const id = window.setTimeout(() => setLeft((v) => v - 1), 1000);
    return () => window.clearTimeout(id);
  }, [left]);

  async function run(kind: "tamper" | "restore") {
    onBusy(true);
    onError(null);
    setRateError(null);
    setDemoMsg(null);
    try {
      if (kind === "tamper") {
        const res = await demoAuditApi.tamper(demoLogId);
        setDemoMsg(`tampered_id=${res.tampered_id}`);
      } else {
        const res = await demoAuditApi.restore(demoLogId);
        setDemoMsg(`restored_id=${res.restored_id}`);
      }
      onVerify(await api.verifyAudit());
      await onStatsRefresh();
    } catch (e) {
      const status = statusOf(e) || (e instanceof ApiError ? e.problem.status : 0);
      if (status === 429) {
        setRateError(e);
        onError(e);
        setDemoMsg("RATE_LIMITED status=429");
      } else if (status === 404) {
        setDemoMsg(t("audit.demoUnavailable"));
      } else if (status === 503) {
        setDemoMsg(t("audit.serviceUnavailable"));
        onError(e);
      } else {
        onError(e);
        setDemoMsg(`demo_error status=${status}`);
      }
    } finally {
      onBusy(false);
    }
  }

  return (
    <section className="panel audit-demo" aria-labelledby="audit-demo-h">
      <h2 id="audit-demo-h" className="audit-section-title">
        {t("audit.demo")}
      </h2>
      <p className="audit-subtitle">{t("audit.demoHint")}</p>
      {rateError ? (
        <div className="banner error-notice audit-rate-limit" role="alert">
          <strong>{t("audit.rateLimitedTitle")}</strong>
          <div>{errorText(rateError)}</div>
          <div className="audit-countdown tabular-nums" aria-live="polite">
            {t("audit.countdown", { seconds: Math.max(left, 0) })}
          </div>
        </div>
      ) : null}
      <div className="action-row">
        <input
          className="input"
          value={demoLogId}
          onChange={(e) => setDemoLogId(e.target.value)}
          aria-label={t("audit.demoLogId")}
          placeholder={t("audit.demoLogId")}
        />
        <button
          className="btn btn-secondary"
          disabled={busy || !demoLogId || rateBlocked || Boolean(rateError)}
          onClick={() => void run("tamper")}
        >
          {t("audit.demoTamper")}
        </button>
        <button
          className="btn btn-secondary"
          disabled={busy || !demoLogId || rateBlocked || Boolean(rateError)}
          onClick={() => void run("restore")}
        >
          {t("audit.demoRestore")}
        </button>
      </div>
      {demoMsg ? (
        <p className="empty-message mono" role="status">
          {demoMsg}
        </p>
      ) : null}
    </section>
  );
}
