import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted } from "../api/http";
import type { ModelChain } from "../api/types";
import { ErrorNotice } from "../components/ErrorNotice";
import { modelDisplay, noHealthyLlm } from "../api/modelStatus";

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
  const noLlm = !!chain && noHealthyLlm(chain);
  return (
    <div className="stack">
      <h1 className="page-title">{t("models.title")}</h1>
      <ErrorNotice error={error} />
      {!chain && !error ? <div role="status">{t("status.running")}</div> : null}
      {chain ? (
        <>
          <div className="banner" data-testid="models-level">
            {t("models.level")}: <strong className="mono">{chain.degrade_level}</strong>
            {chain.llm_provider_chain?.length ? (
              <>
                {" · "}
                {t("models.chain")}:{" "}
                <span className="mono">{chain.llm_provider_chain.join(" → ")}</span>
              </>
            ) : null}
          </div>
          {noLlm ? (
            <div className="banner error-notice" role="status" data-testid="models-no-llm">
              {t("models.noLlm")}
            </div>
          ) : null}
          <div className="panel table-wrap" role="region" aria-label={t("models.title")}>
            <table className="table table-records">
              <thead>
                <tr>
                  <th>{t("models.stage")}</th>
                  <th>Model</th>
                  <th>Provider</th>
                  <th>{t("common.status")}</th>
                  <th>{t("models.calls24h")}</th>
                </tr>
              </thead>
              <tbody>
                {chain.models.map((m) => (
                  <tr key={`${m.category}:${m.provider}:${m.model}`}>
                    <td data-label={t("models.stage")}>
                      {m.stage} · {m.category}
                    </td>
                    <td className="mono" data-label={"Model"}>
                      {modelDisplay(m).name}
                      {modelDisplay(m).note ? (
                        <div className="muted">{modelDisplay(m).note}</div>
                      ) : null}
                    </td>
                    <td data-label={"Provider"}>
                      {m.provider} · {m.deployment}
                    </td>
                    <td data-label={t("common.status")}>
                      {m.healthy ? t("models.healthy") : t("models.unavailable")}
                      {m.circuit_open ? ` · ${t("models.circuitOpen")}` : ""}
                    </td>
                    <td className="tabular-nums" data-label={t("models.calls24h")}>
                      {m.calls_24h ?? "—"}
                      {m.p95_latency_ms != null ? ` · ${m.p95_latency_ms} ms` : ""}
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
