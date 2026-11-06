import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import type { AuditLog, Verify } from "../api/types";
import { ErrorNotice } from "../components/ErrorNotice";
export function AuditPage() {
  const { t } = useTranslation();
  const [query] = useSearchParams();
  const [reviewId, setReviewId] = useState(query.get("review") ?? "");
  const [logs, setLogs] = useState<AuditLog[] | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
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
  return (
    <div className="stack">
      <h1 className="page-title">{t("audit.title")}</h1>
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
        <div className="panel table-wrap">
          {logs.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>{t("common.time")}</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>{t("common.status")}</th>
                  <th>{t("common.requestId")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>
                      {new Date(log.ts).toLocaleString(undefined, {
                        timeZone: "America/Tijuana",
                      })}{" "}
                      (America/Tijuana)
                    </td>
                    <td>{log.actor_username ?? "—"}</td>
                    <td>{log.action}</td>
                    <td>{log.result}</td>
                    <td className="mono">{log.request_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty-message" role="status">
              {t("common.empty")}
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
