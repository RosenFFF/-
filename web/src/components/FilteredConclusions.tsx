import { useTranslation } from "react-i18next";
import { unsupportedFindingCount } from "../api/modelOutputFilter";

/**
 * One line for dropped ungrounded model conclusions on this review.
 * Zero is hidden, including an explicit 0 and a present filter dict that omits
 * unsupported_finding. A missing dictionary is not zero, and it is also hidden.
 * Malformed values render nothing. The sentence is a disclosure of drops.
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
