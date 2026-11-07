import { useTranslation } from "react-i18next";
import { unsupportedFindingCount } from "../api/modelOutputFilter";

/**
 * One line for dropped ungrounded model conclusions on this review.
 * Explicit zero is hidden: the sentence is a disclosure of drops, and a zero
 * would read as a clearance. Missing and malformed values render nothing.
 * Not a live region and not part of the degrade strip.
 */
export function FilteredConclusions({ security }: { security: unknown }) {
  const { t } = useTranslation();
  const parsed = unsupportedFindingCount(security);
  if (parsed.kind !== "count") return null;
  return (
    <p className="filtered-conclusions" data-count={parsed.count}>
      {t("report.filteredUngrounded", { count: parsed.count })}
    </p>
  );
}
