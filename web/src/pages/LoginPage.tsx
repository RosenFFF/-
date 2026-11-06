import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMock } from "../api";
import { ErrorNotice } from "../components/ErrorNotice";
import { useAuth } from "../auth/context";

export function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login, loading, initialError } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState(useMock ? "reviewer" : "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy || loading) return;
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      nav("/cases");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100%",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <form
        className="panel"
        style={{
          width: "min(400px, 100%)",
          padding: 24,
          display: "grid",
          gap: 14,
        }}
        onSubmit={onSubmit}
      >
        <div>
          <div style={{ fontSize: 22, fontWeight: 600 }}>{t("app.name")}</div>
          <div className="muted" style={{ marginTop: 4 }}>
            {t("app.tagline")}
          </div>
        </div>
        <label>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            {t("login.username")}
          </div>
          <input
            required
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            {t("login.password")}
          </div>
          <input
            required
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <ErrorNotice error={error ?? initialError} />
        <button className="btn" type="submit" disabled={busy || loading}>
          {t("login.submit")}
        </button>
        <div className="muted" style={{ fontSize: 12 }}>
          {t(useMock ? "login.hint" : "login.cookieHint")}
        </div>
        <div className="lang-row">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void i18n.changeLanguage("vi")}
          >
            {t("lang.vi")}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void i18n.changeLanguage("zh")}
          >
            {t("lang.zh")}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void i18n.changeLanguage("en")}
          >
            {t("lang.en")}
          </button>
        </div>
      </form>
    </div>
  );
}
