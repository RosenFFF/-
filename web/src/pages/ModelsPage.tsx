import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted } from "../api/http";
import type { ModelChain } from "../api/types";
import { ErrorNotice } from "../components/ErrorNotice";
export function ModelsPage() {
  const { t } = useTranslation();
  const [chain, setChain] = useState<ModelChain | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const c = new AbortController();
    void api
      .models(c.signal)
      .then(setChain)
      .catch((e: unknown) => {
        if (!aborted(e)) setError(e);
      });
    return () => c.abort();
  }, []);
  return (
    <div className="stack">
      <h1 className="page-title">{t("models.title")}</h1>
      <ErrorNotice error={error} />
      {!chain && !error ? <div role="status">{t("status.running")}</div> : null}
      {chain ? (
        <>
          <div className="banner">
            {t("report.degraded")}: {chain.degrade_level}
          </div>
          <div className="panel table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("models.stage")}</th>
                  <th>Model</th>
                  <th>Provider</th>
                  <th>{t("common.status")}</th>
                </tr>
              </thead>
              <tbody>
                {chain.models.map((m, i) => (
                  <tr key={i}>
                    <td>
                      {m.stage} · {m.category}
                    </td>
                    <td className="mono">{m.model}</td>
                    <td>
                      {m.provider} · {m.deployment}
                    </td>
                    <td>
                      {m.healthy
                        ? t("models.healthy")
                        : t("models.unavailable")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
