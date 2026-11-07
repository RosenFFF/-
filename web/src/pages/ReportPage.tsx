import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted } from "../api/http";
import { poll } from "../api/poll";
import type { Language, Finding, Review, Rule } from "../api/types";
import { ErrorNotice } from "../components/ErrorNotice";
import { FlowTrail } from "../components/FlowTrail";
import { languages } from "../api/languages";
import {
  CitationSource,
  ReportRuleSource,
  ReportVerification,
} from "../components/Provenance";

export function ReportPage() {
  const { id = "" } = useParams();
  const [query, setQuery] = useSearchParams();
  const reviewId = query.get("review") ?? "";
  const { t } = useTranslation();
  const [lang, setLang] = useState<Language>("zh-CN");
  const [country, setCountry] = useState("RU");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const creating = useRef(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function start() {
    if (creating.current) return;
    creating.current = true;
    controller.current = new AbortController();
    setBusy(true);
    setError(null);
    try {
      const r = await api.startReview(
        { document_ids: [id], destination_country: country, language: lang },
        controller.current.signal,
      );
      setQuery({ review: r.id });
    } catch (e) {
      if (!aborted(e)) setError(e);
    } finally {
      creating.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <FlowTrail />
      <div className="page-head">
        <h1 className="page-title">{t("report.title")}</h1>
        <div className="action-row">
          <label>
            {t("report.destination")}
            <input
              className="input country-input"
              value={country}
              disabled={!!reviewId || busy}
              onChange={(e) =>
                setCountry(
                  e.target.value
                    .toUpperCase()
                    .replace(/[^A-Z]/g, "")
                    .slice(0, 2),
                )
              }
              maxLength={2}
            />
          </label>
          <label>
            {t("report.answerLang")}
            <select
              className="select"
              value={lang}
              onChange={(e) => setLang(e.target.value as Language)}
            >
              {languages.map((l) => (
                <option key={l} value={l}>
                  {t(`answer.${l === "zh-CN" ? "zh" : l}`)}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn"
            type="button"
            disabled={busy || country.length !== 2}
            onClick={() => {
              if (reviewId) setRetry((r) => r + 1);
              else void start();
            }}
          >
            {busy
              ? t("status.running")
              : reviewId
                ? t("common.retry")
                : t("extract.continue")}
          </button>
        </div>
      </div>
      <ErrorNotice error={error} />
      {!reviewId && !busy && !error ? (
        <div className="banner">{t("report.startHint")}</div>
      ) : null}
      {reviewId ? (
        <ReportResult
          key={`${id}:${reviewId}:${lang}:${retry}`}
          id={id}
          reviewId={reviewId}
          lang={lang}
        />
      ) : null}
    </div>
  );
}
function ReportResult({
  id,
  reviewId,
  lang,
}: {
  id: string;
  reviewId: string;
  lang: Language;
}) {
  const { t } = useTranslation();
  const [report, setReport] = useState<Review | null>(null);
  const [active, setActive] = useState<Finding | null>(null);
  const [rule, setRule] = useState<Rule | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [ruleError, setRuleError] = useState<unknown>(null);
  const [busy, setBusy] = useState(true);
  const citationController = useRef<AbortController | null>(null);
  useEffect(() => {
    const c = new AbortController();
    void poll(
      () => api.review(reviewId, lang, c.signal),
      "completed",
      c.signal,
      setReport,
    )
      .then((r) => {
        if (!c.signal.aborted) setActive(r.findings[0] ?? null);
      })
      .catch((e: unknown) => {
        if (!aborted(e)) setError(e);
      })
      .finally(() => {
        if (!c.signal.aborted) setBusy(false);
      });
    return () => {
      c.abort();
      citationController.current?.abort();
    };
  }, [reviewId, lang]);
  async function loadRule(ruleId: string) {
    citationController.current?.abort();
    citationController.current = new AbortController();
    setRule(null);
    setRuleError(null);
    try {
      const r = await api.rule(ruleId, citationController.current.signal);
      setRule(r);
    } catch (e) {
      if (!aborted(e)) setRuleError(e);
    }
  }
  return (
    <div className="stack">
      <ErrorNotice error={error} />
      {busy ? (
        <div role="status">
          {t("status.running")} {report?.progress?.step}{" "}
          {report?.progress?.percent ?? 0}%
        </div>
      ) : null}
      {report ? (
        <ReportVerification report={report} capability="review" />
      ) : null}
      {report?.status === "completed" ? (
        <Link
          className="btn"
          to={`/cases/${id}/ask?review=${encodeURIComponent(reviewId)}`}
        >
          {t("report.ask")}
        </Link>
      ) : null}
      {report?.status === "completed" ? (
        <>
          <ReportRuleSource report={report} />
          {report.aigc ? (
            <div className="banner aigc-notice">
              {report.aigc.explicit_text}
            </div>
          ) : null}
          <div className="panel summary-strip">
            <strong>
              {t("report.riskSummary")}: {report.risk_level ?? "—"}
            </strong>
            <span>{report.summary}</span>
            <Link to={`/audit?review=${encodeURIComponent(reviewId)}`}>
              {t("audit.own")}
            </Link>
          </div>
          <div className="grid-2">
            <div className="panel">
              <div className="finding-list">
                {report.findings.length ? (
                  report.findings.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`finding${active?.id === f.id ? " selected" : ""}`}
                      aria-pressed={active?.id === f.id}
                      onClick={() => {
                        citationController.current?.abort();
                        setActive(f);
                        setRule(null);
                        setRuleError(null);
                      }}
                    >
                      <span
                        className={`badge badge-${f.severity === "medium" ? "med" : f.severity === "info" ? "pass" : f.severity}`}
                      >
                        {t(`risk.${f.severity}`)}
                      </span>
                      <strong>{f.title}</strong>
                      <span>{f.message}</span>
                      <span className="mono">{f.determined_by}</span>
                    </button>
                  ))
                ) : (
                  <p>{t("report.noFindings")}</p>
                )}
              </div>
            </div>
            <section
              className="panel form-panel"
              aria-label={t("report.citations")}
            >
              <h2 className="section-title">{t("report.citations")}</h2>
              {active?.citations.map((c) => (
                <div className="stack" key={c.rule_id}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => void loadRule(c.rule_id)}
                  >
                    {c.source} · {c.article}
                  </button>
                  <CitationSource value={c} />
                  <blockquote className="serif citation">
                    <span className="citation-body">{c.excerpt}</span>
                  </blockquote>
                </div>
              ))}
              <ErrorNotice error={ruleError} />
              {rule ? (
                <article className="rule-text">
                  <h3>{rule.title}</h3>
                  <div>
                    {rule.source} · {rule.article}
                  </div>
                  <CitationSource value={rule} />
                  <p className="serif">{rule.text}</p>
                </article>
              ) : null}
              {active ? (
                <div className="action-row">
                  {(active.field_keys ?? []).map((key) => (
                    <Link
                      className="btn btn-secondary"
                      key={key}
                      to={`/cases/${active.document_id ?? id}/extract?field=${encodeURIComponent(key)}`}
                    >
                      {t("report.locate")}: {key}
                    </Link>
                  ))}
                  {(active.evidence_block_ids ?? []).map((block) => (
                    <Link
                      className="btn btn-secondary"
                      key={block}
                      to={`/cases/${active.document_id ?? id}/extract?block=${encodeURIComponent(block)}`}
                    >
                      {t("report.locate")}: {block}
                    </Link>
                  ))}
                </div>
              ) : null}
            </section>
          </div>
          <div className="panel table-wrap">
            {report.models?.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("models.stage")}</th>
                    <th>Model</th>
                    <th>ms</th>
                    <th>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {(report.models ?? []).map((m, i) => (
                    <tr key={i}>
                      <td>{m.task}</td>
                      <td className="mono">{m.model}</td>
                      <td>{m.latency_ms}</td>
                      <td>
                        {m.tokens_in ?? "—"} / {m.tokens_out ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="empty-message">{t("models.noCalls")}</p>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
