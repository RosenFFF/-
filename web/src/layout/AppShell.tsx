import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/context";
import { ErrorNotice } from "../components/ErrorNotice";
import "./shell.css";
export function AppShell() {
  const { t, i18n } = useTranslation();
  const { session, logout, role } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const documentId = location.pathname.match(/^\/cases\/([^/]+)\//)?.[1];
  const links = [
    ["cases", "/cases"],
    ["upload", "/cases/new"],
    ...(documentId
      ? [
          ["extract", `/cases/${documentId}/extract`],
          ["report", `/cases/${documentId}/report${location.search}`],
          ["ask", `/cases/${documentId}/ask${location.search}`],
        ]
      : []),
    ["audit", "/audit"],
    ["models", "/system/models"],
  ];
  async function signOut() {
    setBusy(true);
    setError(null);
    try {
      await logout();
      nav("/login");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        {t("common.skipToContent")}
      </a>
      <aside className="shell-nav" aria-label={t("app.name")}>
        <div className="brand">
          <div className="brand-name">{t("app.name")}</div>
          <div className="brand-tag muted">{t("app.tagline")}</div>
        </div>
        <nav>
          {links.map(([key, to]) => (
            <NavLink
              key={key}
              to={to}
              end
              className={({ isActive }) =>
                isActive ? "nav-item active" : "nav-item"
              }
            >
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
        <div className="nav-foot">
          <div>
            {session?.username} · {t(`role.${role}`)}
          </div>
          <div className="lang-row">
            {["zh", "en", "vi"].map((l) => (
              <button
                key={l}
                type="button"
                className="btn btn-ghost"
                onClick={() => void i18n.changeLanguage(l)}
              >
                {t(`lang.${l}`)}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void signOut()}
          >
            {t("nav.logout")}
          </button>
          <ErrorNotice error={error} />
        </div>
      </aside>
      <main id="main-content" className="shell-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
