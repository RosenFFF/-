import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

const STEPS = ["upload", "extract", "report", "ask", "audit"] as const;
type Step = (typeof STEPS)[number];

function currentStep(pathname: string): Step | null {
  if (pathname.endsWith("/new") || pathname.includes("/cases/new")) return "upload";
  if (pathname.includes("/extract")) return "extract";
  if (pathname.includes("/report")) return "report";
  if (pathname.includes("/ask")) return "ask";
  if (pathname.includes("/audit")) return "audit";
  return null;
}

/** Compact case-flow trail — desk-review continuity, not a marketing stepper. */
export function FlowTrail() {
  const { t } = useTranslation();
  const location = useLocation();
  const { id } = useParams();
  const [query] = useSearchParams();
  const review = query.get("review");
  const active = currentStep(location.pathname);
  if (!active) return null;

  const href: Record<Step, string | null> = {
    upload: "/cases/new",
    extract: id ? `/cases/${id}/extract` : null,
    report: id ? `/cases/${id}/report${review ? `?review=${encodeURIComponent(review)}` : ""}` : null,
    ask: id
      ? `/cases/${id}/ask${review ? `?review=${encodeURIComponent(review)}` : ""}`
      : null,
    audit: "/audit",
  };

  return (
    <nav className="flow-trail" aria-label={t("flow.label")}>
      <ol className="flow-trail-list">
        {STEPS.map((step, index) => {
          const isActive = step === active;
          const to = href[step];
          const reached =
            STEPS.indexOf(active) >= index || step === "audit" || step === "upload";
          const label = t(`flow.${step}`);
          return (
            <li
              key={step}
              className={
                isActive
                  ? "flow-trail-item is-active"
                  : reached
                    ? "flow-trail-item is-reached"
                    : "flow-trail-item"
              }
              aria-current={isActive ? "step" : undefined}
            >
              {to && !isActive && reached ? (
                <Link to={to} className="flow-trail-link">
                  <span className="flow-trail-index tabular-nums">{index + 1}</span>
                  {label}
                </Link>
              ) : (
                <span className="flow-trail-link">
                  <span className="flow-trail-index tabular-nums">{index + 1}</span>
                  {label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
