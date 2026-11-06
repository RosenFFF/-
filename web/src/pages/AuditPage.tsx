import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { ApiError } from "../api/http";
import { errorText } from "../api/errors";
import type {
  AuditLog,
  AuditResult,
  AuditWindow,
  SecurityStats,
  SecurityTotals,
  Verify,
} from "../api/types";
import { ErrorNotice } from "../components/ErrorNotice";
import { RateLimitNotice } from "../components/RateLimitNotice";

const WINDOWS: AuditWindow[] = ["1h", "24h", "7d"];

const METRIC_KEYS: (keyof SecurityTotals)[] = [
  "requests",
  "logins_failed",
  "access_denied",
  "rate_limited",
  "injections_blocked",
  "outputs_blocked",
  "pii_masked",
  "csrf_failed",
  "auth_locked",
  "model_calls",
  "model_fallbacks",
  "model_errors",
  "tokens_used",
];

function formatTs(iso: string): string {
  return `${new Date(iso).toLocaleString(undefined, {
    timeZone: "America/Tijuana",
  })} (America/Tijuana)`;
}

function Marker({
  kind,
  children,
}: {
  kind: "source" | "fallback" | "missing" | "degrade" | "ok";
  children: string;
}) {
  return (
    <span className={`audit-marker audit-marker--${kind}`} role="status">
      {children}
    </span>
  );
}

function isRateLimited(error: unknown): boolean {
  return error instanceof ApiError && error.problem.status === 429;
}

function isUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.problem.status === 503 ||
      error.problem.code === "RATE_LIMIT_UNAVAILABLE")
  );
}

export function AuditPage() {
  const { t } = useTranslation();
  const [query] = useSearchParams();
  const windowLabelId = useId();
  const [reviewId, setReviewId] = useState(query.get("review") ?? "");
  const [window, setWindow] = useState<AuditWindow>("24h");
  const [actionFilter, setActionFilter] = useState("");
  const [resultFilter, setResultFilter] = useState<AuditResult | "">("");
  const [logs, setLogs] = useState<AuditLog[] | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [stats, setStats] = useState<SecurityStats | null>(null);
  const [statsError, setStatsError] = useState<unknown>(null);
  const [statsBusy, setStatsBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [rateError, setRateError] = useState<unknown>(null);
  const [seedDemoLogId, setSeedDemoLogId] = useState("");
  const [DemoPanel, setDemoPanel] = useState<null | typeof import("../components/DemoAuditPanel").DemoAuditPanel>(null);

  const captureError = useCallback((e: unknown) => {
    if (isRateLimited(e)) setRateError(e);
    return e;
  }, []);

  const loadStats = useCallback(
    async (signal?: AbortSignal) => {
      setStatsBusy(true);
      setStatsError(null);
      try {
        const next = await api.auditStats(window, signal);
        if (!signal?.aborted) setStats(next);
      } catch (e) {
        if (signal?.aborted) return;
        setStats(null);
        setStatsError(captureError(e));
      } finally {
        if (!signal?.aborted) setStatsBusy(false);
      }
    },
    [window, captureError],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    void loadStats(ctrl.signal);
    return () => ctrl.abort();
  }, [loadStats]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    let cancelled = false;
    void import("../components/DemoAuditPanel").then((mod) => {
      if (!cancelled) setDemoPanel(() => mod.DemoAuditPanel);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function load(own = false) {
    setBusy(true);
    setError(null);
    setLogs(null);
    try {
      const page = await api.audit(own ? reviewId : undefined, {
        action: actionFilter || undefined,
        result: resultFilter || undefined,
        page_size: 50,
      });
      setLogs(page.items);
      const denied = page.items.find((item) => item.result === "denied");
      if (denied) setSeedDemoLogId(denied.id);
    } catch (e) {
      setError(captureError(e));
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setBusy(true);
    setError(null);
    setVerify(null);
    try {
      setVerify(await api.verifyAudit());
    } catch (e) {
      setError(captureError(e));
    } finally {
      setBusy(false);
    }
  }


  const timelineMax = useMemo(() => {
    const buckets = stats?.timeline ?? [];
    let max = 0;
    for (const bucket of buckets) {
      const sum =
        (bucket.access_denied ?? 0) +
        (bucket.injections_blocked ?? 0) +
        (bucket.rate_limited ?? 0) +
        (bucket.model_calls ?? 0) +
        (bucket.logins_failed ?? 0) +
        (bucket.pii_masked ?? 0);
      if (sum > max) max = sum;
    }
    return max || 1;
  }, [stats]);

  const chainState =
    stats?.audit_chain_valid === true
      ? "ok"
      : stats?.audit_chain_valid === false
        ? "bad"
        : "unknown";

  return (
    <div className="stack audit-page">
      <header className="audit-header">
        <div>
          <h1 className="page-title">{t("audit.title")}</h1>
          <p className="audit-subtitle">{t("audit.subtitle")}</p>
        </div>
      </header>

      <RateLimitNotice error={rateError} onExpire={() => setRateError(null)} />

      <section
        className="panel audit-stats"
        aria-labelledby="audit-stats-heading"
      >
        <div className="audit-stats-toolbar">
          <h2 id="audit-stats-heading" className="audit-section-title">
            {t("audit.stats")}
          </h2>
          <div
            className="audit-window"
            role="group"
            aria-labelledby={windowLabelId}
          >
            <span id={windowLabelId} className="audit-window-label">
              {t("audit.window")}
            </span>
            {WINDOWS.map((value) => (
              <button
                key={value}
                type="button"
                className={
                  window === value ? "btn btn-chip is-active" : "btn btn-chip"
                }
                aria-pressed={window === value}
                disabled={statsBusy || Boolean(rateError)}
                onClick={() => setWindow(value)}
              >
                {t(`audit.window.${value}`)}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-secondary"
              disabled={statsBusy || Boolean(rateError)}
              onClick={() => void loadStats()}
            >
              {t("audit.loadStats")}
            </button>
          </div>
        </div>

        {statsBusy && !stats ? (
          <p className="empty-message" role="status">
            {t("audit.statsLoading")}
          </p>
        ) : null}

        {statsError && !isRateLimited(statsError) ? (
          <div
            className="banner error-notice"
            role={isUnavailable(statsError) ? "alert" : "status"}
          >
            {isUnavailable(statsError)
              ? t("audit.serviceUnavailable") + " · "
              : ""}
            {errorText(statsError)}
          </div>
        ) : null}

        {stats ? (
          <>
            <div className="audit-meta-row">
              <span
                className={`audit-chain audit-chain--${chainState}`}
                role="status"
              >
                {chainState === "ok"
                  ? t("audit.chainOk")
                  : chainState === "bad"
                    ? t("audit.chainBad")
                    : t("audit.chainUnknown")}
              </span>
              <span className="audit-window-value mono">
                {t("audit.windowRange")}: {formatTs(stats.window_start)} →{" "}
                {formatTs(stats.window_end)}
              </span>
              <span className="audit-window-value mono">
                {t("audit.generatedAt")}: {formatTs(stats.generated_at)}
              </span>
              {stats.degrade_status?.trim() ? (
                <Marker kind="degrade">{stats.degrade_status.trim()}</Marker>
              ) : (
                <Marker kind="missing">{t("report.statusMissing")}</Marker>
              )}
              {stats.llm_verified ? (
                <Marker kind="ok">{t("report.llmVerified.true")}</Marker>
              ) : (
                <Marker kind="fallback">{t("audit.llmUnverified")}</Marker>
              )}
              {stats.source_kind_label?.trim() ? (
                <Marker kind="source">{stats.source_kind_label.trim()}</Marker>
              ) : (
                <Marker kind="missing">{t("source.missing")}</Marker>
              )}
            </div>

            <ul className="audit-metrics">
              {METRIC_KEYS.map((key) => (
                <li key={key} className="audit-metric">
                  <span className="audit-metric-label">
                    {t(`audit.metric.${key}`)}
                  </span>
                  <span className="audit-metric-value tabular-nums">
                    {stats.totals[key] ?? "—"}
                  </span>
                </li>
              ))}
            </ul>

            <div className="audit-split">
              <section className="audit-timeline">
                <h3 className="audit-section-title">{t("audit.timeline")}</h3>
                {stats.timeline?.length ? (
                  <ul className="audit-bars">
                    {stats.timeline.map((bucket) => {
                      const sum =
                        (bucket.access_denied ?? 0) +
                        (bucket.injections_blocked ?? 0) +
                        (bucket.rate_limited ?? 0) +
                        (bucket.model_calls ?? 0) +
                        (bucket.logins_failed ?? 0) +
                        (bucket.pii_masked ?? 0);
                      const pct = Math.round((sum / timelineMax) * 100);
                      return (
                        <li key={bucket.bucket_start} className="audit-bar-row">
                          <span className="audit-bar-label mono">
                            {formatTs(bucket.bucket_start)}
                          </span>
                          <div
                            className="audit-bar-track"
                            role="img"
                            aria-label={`${sum}`}
                          >
                            <span
                              className="audit-bar-fill"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="audit-bar-sum tabular-nums">
                            {sum}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="empty-message" role="status">
                    {t("audit.timelineEmpty")}
                  </p>
                )}
              </section>

              <section className="audit-top">
                <h3 className="audit-section-title">{t("audit.topDenied")}</h3>
                {stats.top_denied_actors?.length ? (
                  <ul className="audit-top-list">
                    {stats.top_denied_actors.map((actor, index) => (
                      <li
                        key={`${actor.actor_username ?? "unknown"}-${index}`}
                        className="audit-top-item"
                      >
                        <span>{actor.actor_username ?? "—"}</span>
                        <span className="tabular-nums">{actor.count}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty-message" role="status">
                    {t("audit.topDeniedEmpty")}
                  </p>
                )}
              </section>
            </div>
          </>
        ) : null}
      </section>

      <section
        className="panel audit-logs"
        aria-labelledby="audit-logs-heading"
      >
        <h2 id="audit-logs-heading" className="audit-section-title">
          {t("audit.logs")}
        </h2>
        <div className="action-row">
          <input
            className="input"
            value={reviewId}
            onChange={(e) => setReviewId(e.target.value)}
            aria-label={t("audit.reviewId")}
            placeholder={t("audit.reviewId")}
          />
          <input
            className="input"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            aria-label={t("audit.filterAction")}
            placeholder={t("audit.filterAction")}
          />
          <select
            className="input"
            value={resultFilter}
            onChange={(e) =>
              setResultFilter((e.target.value || "") as AuditResult | "")
            }
            aria-label={t("audit.filterResult")}
          >
            <option value="">{t("audit.filterResult")}</option>
            <option value="success">success</option>
            <option value="denied">denied</option>
            <option value="blocked">blocked</option>
            <option value="failed">failed</option>
          </select>
          <button
            className="btn btn-secondary"
            disabled={busy || !reviewId || Boolean(rateError)}
            onClick={() => void load(true)}
          >
            {t("audit.own")}
          </button>
          <button
            className="btn btn-secondary"
            disabled={busy || Boolean(rateError)}
            onClick={() => void load()}
          >
            {t("audit.global")}
          </button>
          <button
            className="btn"
            disabled={busy || Boolean(rateError)}
            onClick={() => void check()}
          >
            {t("audit.verify")}
          </button>
        </div>
        {error && !isRateLimited(error) ? <ErrorNotice error={error} /> : null}
        {verify ? (
          <div className="banner">
            {verify.valid
              ? t("audit.verified")
              : `${t("audit.broken")}: ${verify.first_broken_id}`}{" "}
            · {verify.checked}
            <div className="mono">{verify.head_hash ?? "—"}</div>
          </div>
        ) : null}
        {logs ? (
          <div className="table-wrap">
            {logs.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("common.time")}</th>
                    <th>{t("audit.actor")}</th>
                    <th>{t("audit.action")}</th>
                    <th>{t("audit.resource")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("audit.provenanceMarker")}</th>
                    <th>{t("audit.injection")}</th>
                    <th>{t("audit.piiFields")}</th>
                    <th>{t("common.requestId")}</th>
                    <th>{t("audit.hash")}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => {
                    const detail = log.detail;
                    const inj = detail?.injection_category;
                    const pii = detail?.pii_fields;
                    return (
                      <tr key={log.id}>
                        <td>{formatTs(log.ts)}</td>
                        <td>
                          {log.actor_username ?? "—"}
                          {log.actor_role ? (
                            <span className="audit-role">
                              {" "}
                              · {log.actor_role}
                            </span>
                          ) : null}
                        </td>
                        <td>{log.action}</td>
                        <td className="mono">
                          {log.resource_type || log.resource_id
                            ? `${log.resource_type ?? "—"}/${log.resource_id ?? "—"}`
                            : "—"}
                        </td>
                        <td>{log.result}</td>
                        <td>
                          <div className="audit-markers">
                            {detail?.source_kind_label ? (
                              <Marker kind="source">
                                {detail.source_kind_label}
                              </Marker>
                            ) : (
                              <Marker kind="missing">
                                {t("source.missing")}
                              </Marker>
                            )}
                            {detail?.degrade_status ? (
                              <Marker kind="degrade">
                                {detail.degrade_status}
                              </Marker>
                            ) : null}
                            {detail?.llm_verified === true ? (
                              <Marker kind="ok">
                                {t("report.llmVerified.true")}
                              </Marker>
                            ) : (
                              <Marker kind="fallback">
                                {t("audit.llmUnverified")}
                              </Marker>
                            )}
                            {detail?.fallback_reason ? (
                              <Marker kind="degrade">
                                {`${t("audit.fallbackReason")}: ${detail.fallback_reason}`}
                              </Marker>
                            ) : null}
                            {detail?.rate_limit_scope ? (
                              <Marker kind="source">
                                {`${t("audit.rateLimitScope")}: ${detail.rate_limit_scope}`}
                              </Marker>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          {inj ? t(`injection.${inj}`) : "—"}
                        </td>
                        <td className="mono">
                          {pii?.length ? pii.join(", ") : "—"}
                        </td>
                        <td className="mono">{log.request_id}</td>
                        <td className="mono">{log.hash}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="empty-message" role="status">
                {t("common.empty")}
              </p>
            )}
          </div>
        ) : null}
      </section>

      {DemoPanel ? (
        <DemoPanel
          busy={busy}
          rateBlocked={Boolean(rateError)}
          onBusy={setBusy}
          onError={(e) => {
            if (e) captureError(e);
            setError(e);
          }}
          onVerify={setVerify}
          onStatsRefresh={() => loadStats()}
          initialLogId={seedDemoLogId}
        />
      ) : null}
    </div>
  );
}
