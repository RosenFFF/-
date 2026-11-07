import { useTranslation } from "react-i18next";
import type { ProvenanceView } from "../api/degradeStatus";

/**
 * One sober strip for a single capability. It does not take focus and, unless
 * `live`, is not a live region — chat rows sit beside streaming text and must
 * not announce on every token or on history load.
 */
export function DegradeStrip({
  view,
  live = false,
  className = "",
  testId,
}: {
  view: ProvenanceView;
  live?: boolean;
  className?: string;
  testId?: string;
}) {
  const { t } = useTranslation();
  const level =
    view.level.kind === "known"
      ? view.level.level
      : view.level.kind === "missing"
        ? t("degrade.level.missing")
        : t("degrade.level.unrecognized");
  const showsRecordFields = view.capability === "extraction" || view.capability === "review";
  const source =
    view.source.kind === "none"
      ? t("degrade.source.missing")
      : view.source.kind === "trace"
        ? t("degrade.source.trace", {
            provider: view.source.provider,
            model: view.source.model,
            status: view.source.status,
          })
        : t("degrade.source.health", {
            provider: view.source.provider,
            model: view.source.model,
            deployment: view.source.deployment,
          });
  return (
    <div
      className={`degrade-strip${className ? ` ${className}` : ""}`}
      data-capability={view.capability}
      data-scope={view.scope}
      data-level={view.level.kind === "known" ? view.level.level : view.level.kind}
      data-testid={testId}
      role={live ? "status" : undefined}
      aria-live={live ? "polite" : "off"}
      aria-atomic={live ? true : undefined}
    >
      <div className="degrade-strip-row">
        <strong>{t(`degrade.capability.${view.capability}`)}</strong>
        <span>
          {t("degrade.levelLabel")}: <span className="mono">{level}</span>
        </span>
      </div>
      <p>{t(`degrade.scope.${view.scope}`)}</p>
      {showsRecordFields ? (
        <p>
          <span>{t("degrade.serverStatusLabel")}: </span>
          <strong>{view.serverStatus ?? t("report.statusMissing")}</strong>
        </p>
      ) : null}
      {showsRecordFields ? (
        <p>
          {t("report.llmVerified")}:{" "}
          {view.llmVerified === true
            ? t("report.llmVerified.true")
            : view.llmVerified === false
              ? t("report.llmVerified.false")
              : t("report.statusMissing")}
        </p>
      ) : null}
      <p>
        {t("degrade.sourceLabel")}: {source}
        {view.localCaveat ? ` ${t("degrade.source.localCaveat")}` : null}
      </p>
      {view.chain ? (
        <p>
          {t("degrade.chainLabel")}: <span className="mono">{view.chain.join(" → ")}</span>
        </p>
      ) : null}
      {view.blocked ? <p>{t("degrade.blocked")}</p> : null}
      <p>{t("degrade.limitLabel")}</p>
      {view.limits.map((key) => (
        <p key={key}>{t(`degrade.limit.${key}`)}</p>
      ))}
      {view.positioning ? <p>{t("degrade.positioning")}</p> : null}
    </div>
  );
}
