import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { ApiError } from "../api/http";
import type {
  AuditLog,
  AuditWindow,
  SecurityStats,
  SecurityTotals,
  Verify,
} from "../api/types";
import { errorText } from "../api/errors";
import { ErrorNotice } from "../components/ErrorNotice";

const WINDOWS: AuditWindow[] = ["1h", "24h", "7d"];

const METRIC_KEYS: (keyof SecurityTotals)[] = [
  "requests",
  "logins_failed",
  "access_denied",
  "rate_limited",
  "injections_blocked",
  "pii_masked",
  "model_calls",
  "model_fallbacks",
  "tokens_used",
];

function formatTs(iso: string): string {
  return `${new Date(iso).toLocaleString(undefined, {
    timeZone: "America/Tijuana",
  })} (America/Tijuana)`;
}

function detailText(
  detail: Record<string, unknown> | undefined,
  key: string,
): string | null {
  const value = detail?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function detailBool(
  detail: Record<string, unknown> | undefined,
  key: string,
): boolean | null {
  const value = detail?.[key];
  return typeof value === "boolean" ? value : null;
}

function Marker({
  kind,
  children,
}: {
  kind: "source" | "fallback" | "missing" | "degrade";
  children: string;
}) {
  return (
    <span className={`audit-marker audit-marker--${kind}`} role="status">
      {children}
    </span>
  );
}

function StatsErrorText({ error }: { error: unknown }) {
  return <>{errorText(error)}</>;
}

export function AuditPage() {
  const { t } = useTranslation();
  const [query] = useSearchParams();
  const windowLabelId = useId();
  const [reviewId, setReviewId] = useState(query.get("review") ?? "");
  const [window, setWindow] = useState<AuditWindow>("24h");
  const [logs, setLogs] = useState<AuditLog[] | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [stats, setStats] = useState<SecurityStats | null>(null);
  const [statsError, setStatsError] = useState<unknown>(null);
  const [statsBusy, setStatsBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

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
        setStatsError(e);
      } finally {
        if (!signal?.aborted) setStatsBusy(false);
      }
    },
    [window],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    void loadStats(ctrl.signal);
    return () => ctrl.abort();
  }, [loadStats]);

  async function load(own = false) {
    setBusy(true);
    setError(null);
    setLogs(null);
    try {
      setLogs((await api.audit(own ? reviewId : undefined)).items);
    } catch (e) {
      setError(e);
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
      setError(e);
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
        (bucket.model_calls ?? 0);
      if (sum > max) max = sum;
    }
    return max || 1;
  }, [stats]);

  const statsUnavailable =
    statsError instanceof ApiError &&
    (statsError.problem.status === 501 || statsError.problem.status === 503);

  const chainState =
    stats?.audit_chain_valid === true
      ? "ok"
      : stats?.audit_chain_valid === false
        ? "bad"
        : "unknown";

  const statsExtra = stats as
    | (SecurityStats & {
        degrade_status?: string | null;
        llm_verified?: boolean | null;
        source_kind?: string | null;
        source_kind_label?: string | null;
      })
    | null;

  return (
    <div className="stack audit-page">
      <header className="audit-header">
        <div>
          <h1 className="page-title">{t("audit.title")}</h1>
          <p className="audit-subtitle">{t("audit.subtitle")}</p>
        </div>
        <p className="audit-backend-note">
          {t("audit.backendPending")}
        </p>
      </header>

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
                disabled={statsBusy}
                onClick={() => setWindow(value)}
              >
                {t(`audit.window.${value}`)}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-secondary"
              disabled={statsBusy}
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

        {statsError ? (
          <div
            className={statsUnavailable ? "banner error-notice" : "banner error-notice"}
            role={statsUnavailable ? "alert" : "status"}
          >
            {statsUnavailable ? t("audit.statsUnavailable") + " · " : ""}
            {/* reuse ErrorNotice text path */}
            <StatsErrorText error={statsError} />
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
              <span className="audit-window-value mono">{stats.window}</span>
              {statsExtra?.degrade_status?.trim() ? (
                <Marker kind="degrade">{statsExtra.degrade_status.trim()}</Marker>
              ) : null}
              {typeof statsExtra?.llm_verified === "boolean" ? (
                statsExtra.llm_verified ? null : (
                  <Marker kind="fallback">{t("audit.fallbackMarker")}</Marker>
                )
              ) : (
                <Marker kind="missing">{t("report.statusMissing")}</Marker>
              )}
              {statsExtra?.source_kind_label?.trim() ? (
                <Marker kind="source">
                  {statsExtra.source_kind_label.trim()}
                </Marker>
              ) : statsExtra?.source_kind ? (
                <Marker kind="missing">{t("source.missing")}</Marker>
              ) : null}
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
                <h3 className="audit-section-title">
                  {t("audit.timeline")}
                </h3>
                {stats.timeline?.length ? (
                  <ul className="audit-bars">
                    {stats.timeline.map((bucket) => {
                      const sum =
                        (bucket.access_denied ?? 0) +
                        (bucket.injections_blocked ?? 0) +
                        (bucket.rate_limited ?? 0) +
                        (bucket.model_calls ?? 0);
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
                <h3 className="audit-section-title">
                  {t("audit.topDenied")}
                </h3>
                {stats.top_denied_actors?.length ? (
                  <ul className="audit-top-list">
                    {stats.top_denied_actors.map((actor, index) => (
                      <li
                        key={`${actor.actor_username ?? "unknown"}-${index}`}
                        className="audit-top-item"
                      >
                        <span>{actor.actor_username ?? "—"}</span>
                        <span className="tabular-nums">{actor.count ?? 0}</span>
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
          <button
            className="btn btn-secondary"
            disabled={busy || !reviewId}
            onClick={() => void load(true)}
          >
            {t("audit.own")}
          </button>
          <button
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void load()}
          >
            {t("audit.global")}
          </button>
          <button className="btn" disabled={busy} onClick={() => void check()}>
            {t("audit.verify")}
          </button>
        </div>
        <ErrorNotice error={error} />
        {verify ? (
          <div className="banner">
            {verify.valid
              ? t("audit.verified")
              : `${t("audit.broken")}: ${verify.first_broken_id}`}{" "}
            · {verify.checked}
            <div className="mono">{verify.head_hash}</div>
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
                    <th>{t("common.requestId")}</th>
                    <th>{t("audit.hash")}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => {
                    const sourceLabel = detailText(
                      log.detail,
                      "source_kind_label",
                    );
                    const sourceKind = detailText(log.detail, "source_kind");
                    const degrade = detailText(log.detail, "degrade_status");
                    const llmVerified = detailBool(log.detail, "llm_verified");
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
                            {sourceLabel ? (
                              <Marker kind="source">{sourceLabel}</Marker>
                            ) : sourceKind ? (
                              <Marker kind="missing">
                                {t("source.missing")}
                              </Marker>
                            ) : (
                              <Marker kind="missing">
                                {t("report.statusMissing")}
                              </Marker>
                            )}
                            {degrade ? (
                              <Marker kind="degrade">{degrade}</Marker>
                            ) : null}
                            {llmVerified === false ? (
                              <Marker kind="fallback">
                                {t("audit.fallbackMarker")}
                              </Marker>
                            ) : null}
                          </div>
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
    </div>
  );
}
