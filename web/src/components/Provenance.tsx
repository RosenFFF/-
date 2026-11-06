import { useTranslation } from "react-i18next";
import type { Review, SourceMetadata } from "../api/types";
import {
  applicability,
  degradeStatusText,
  excerptKind,
  sourceKind,
  sourceKindLabel,
  sourceText,
  sourceUrl,
} from "../api/provenance";

type DegradeCarrier = {
  degrade_level?: Review["degrade_level"] | string;
  degrade_status?: string | null;
  llm_verified?: boolean | null;
};

/** Always show wire degrade_status; never substitute fixed frontend L0–L3 copy. */
export function ReportVerification({ report }: { report: DegradeCarrier }) {
  const { t } = useTranslation();
  const status = degradeStatusText(report);
  const verified = report.llm_verified;
  return (
    <div
      className="banner report-verification"
      role="status"
      aria-label={t("report.verificationLabel")}
    >
      <div className="verification-copy">
        <strong>{status ?? t("report.statusMissing")}</strong>
        <span>
          {t("report.llmVerified")}:{" "}
          {verified === true
            ? t("report.llmVerified.true")
            : verified === false
              ? t("report.llmVerified.false")
              : t("report.statusMissing")}
        </span>
      </div>
      <span className="mono">{report.degrade_level}</span>
    </div>
  );
}

/** Aggregate corpus information is separate from both model verification and each citation. */
export function ReportRuleSource({ report }: { report: Review }) {
  const { t } = useTranslation();
  const kind = sourceKind(report.security?.source_kind);
  const label = sourceText(report.security?.source_kind_label);
  const corpusLabel = sourceText(report.security?.rule_corpus_label);
  const retrieval = report.security?.retrieval_mode;
  const disclaimer = sourceText(report.security?.compliance_disclaimer);
  return (
    <section
      className="report-rule-source"
      aria-label={t("source.reportLabel")}
    >
      <strong>{label ?? t("source.missing")}</strong>
      {kind === "public" ? <p>{t("source.publicDisclaimer")}</p> : null}
      {corpusLabel ? <p>{corpusLabel}</p> : null}
      {disclaimer ? <p>{disclaimer}</p> : null}
      {retrieval === "bge" || retrieval === "lightweight_hash" ? (
        <p>
          {t("source.retrieval")}: {t(`source.retrieval.${retrieval}`)}
        </p>
      ) : null}
    </section>
  );
}

export function CitationSource({ value }: { value: SourceMetadata }) {
  const { t } = useTranslation();
  const kind = sourceKind(value.source_kind);
  const label = sourceKindLabel(value);
  const url = sourceUrl(value.url);
  const article = sourceText(value.article);
  const version = sourceText(value.version_date);
  const excerpt = excerptKind(value.excerpt_kind);
  const apply = applicability(value.applicability);
  const missing = t("source.missing");
  // summary excerpt or public kind: never imply original regulation / compliance pass.
  const showSummaryDisclaimer = excerpt === "summary" || kind === "public";
  return (
    <div className="citation-source" data-source-kind={kind ?? "missing"}>
      <strong className="source-kind">{label ?? missing}</strong>
      {showSummaryDisclaimer ? (
        <p className="source-disclaimer">{t("source.publicDisclaimer")}</p>
      ) : null}
      {apply === "unverified" ? (
        <p className="source-disclaimer">{t("source.applicabilityUnverified")}</p>
      ) : null}
      <dl className="source-details">
        <div>
          <dt>{t("source.url")}</dt>
          <dd>
            {url ? (
              <a href={url} target="_blank" rel="noopener noreferrer">
                {url}
              </a>
            ) : (
              missing
            )}
          </dd>
        </div>
        <div>
          <dt>{t("source.article")}</dt>
          <dd>{article ?? missing}</dd>
        </div>
        <div>
          <dt>{t("source.versionDate")}</dt>
          <dd>{version ?? missing}</dd>
        </div>
        <div>
          <dt>{t("source.excerptKind")}</dt>
          <dd>
            {excerpt ? t(`source.excerptKind.${excerpt}`) : missing}
          </dd>
        </div>
        <div>
          <dt>{t("source.applicability")}</dt>
          <dd>
            {apply ? t("source.applicability.unverified") : missing}
          </dd>
        </div>
      </dl>
    </div>
  );
}
