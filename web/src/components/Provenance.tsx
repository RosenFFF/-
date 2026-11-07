import { useTranslation } from "react-i18next";
import { recordProvenance } from "../api/degradeStatus";
import type { Review, SourceMetadata } from "../api/types";
import {
  applicability,
  excerptKind,
  sourceKind,
  sourceKindLabel,
  sourceText,
  sourceUrl,
} from "../api/provenance";
import { DegradeStrip } from "./DegradeStrip";

type DegradeCarrier = {
  degrade_level?: Review["degrade_level"] | string;
  degrade_status?: string | null;
  llm_verified?: boolean | null;
  models?: Review["models"];
};

/**
 * Historical extraction or review strip. Wire degrade_status is shown as returned.
 * Capability defaults to review so existing report call sites stay on that scope.
 */
export function ReportVerification({
  report,
  capability = "review",
}: {
  report: DegradeCarrier;
  capability?: "extraction" | "review";
}) {
  return (
    <DegradeStrip
      view={recordProvenance(capability, report)}
      live
      className="report-verification"
    />
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
  // Synthetic rules often have no public URL/date; never invent one. Public keeps generic missing.
  const urlAbsent =
    kind === "synthetic" ? t("source.noPublicUrl") : missing;
  const versionAbsent =
    kind === "synthetic" ? t("source.versionAbsent") : missing;
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
              urlAbsent
            )}
          </dd>
        </div>
        <div>
          <dt>{t("source.article")}</dt>
          <dd>{article ?? missing}</dd>
        </div>
        <div>
          <dt>{t("source.versionDate")}</dt>
          <dd>{version ?? versionAbsent}</dd>
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
