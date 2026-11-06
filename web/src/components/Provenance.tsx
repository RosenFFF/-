import { useTranslation } from "react-i18next";
import type { Review, SourceMetadata } from "../api/types";
import {
  sourceKind,
  sourceText,
  sourceUrl,
  verificationKey,
} from "../api/provenance";

export function ReportVerification({ report }: { report: Review }) {
  const { t } = useTranslation();
  return (
    <div
      className="banner report-verification"
      role="status"
      aria-label={t("report.verificationLabel")}
    >
      <strong>{t(verificationKey(report))}</strong>
      <span className="mono">{report.degrade_level}</span>
    </div>
  );
}
// Aggregate corpus information is separate from both model verification and each citation.
export function ReportRuleSource({ report }: { report: Review }) {
  const { t } = useTranslation();
  const kind = sourceKind(report.security?.source_kind);
  const retrieval = report.security?.retrieval_mode;
  const disclaimer = sourceText(report.security?.compliance_disclaimer);
  return (
    <section
      className="report-rule-source"
      aria-label={t("source.reportLabel")}
    >
      <strong>{kind ? t(`source.${kind}`) : t("source.missing")}</strong>
      {kind === "public" ? <p>{t("source.publicDisclaimer")}</p> : null}
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
  const url = sourceUrl(value.url);
  const article = sourceText(value.article);
  const version = sourceText(value.version_date);
  const missing = t("source.missing");
  return (
    <div className="citation-source" data-source-kind={kind ?? "missing"}>
      <strong className="source-kind">
        {kind ? t(`source.${kind}`) : missing}
      </strong>
      {kind === "public" ? (
        <p className="source-disclaimer">{t("source.publicDisclaimer")}</p>
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
      </dl>
    </div>
  );
}
