import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState('reviewer');
  const [password, setPassword] = useState('demo');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await login(username, password);
      nav('/cases');
    } catch {
      setError(t('login.error'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: '100%', display: 'grid', placeItems: 'center', padding: 24 }}>
      <form className="panel" style={{ width: 400, padding: 24, display: 'grid', gap: 14 }} onSubmit={onSubmit}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 600 }}>{t('app.name')}</div>
          <div className="muted" style={{ marginTop: 4 }}>{t('app.tagline')}</div>
        </div>
        <label>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{t('login.username')}</div>
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{t('login.password')}</div>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error ? <div style={{ color: 'var(--risk-high)', fontSize: 13 }}>{error}</div> : null}
        <button className="btn" type="submit" disabled={busy}>{t('login.submit')}</button>
        <div className="muted" style={{ fontSize: 12 }}>{t('login.hint')}</div>
        <div className="lang-row">
          <button type="button" className="btn btn-ghost" onClick={() => void i18n.changeLanguage('zh')}>{t('lang.zh')}</button>
          <button type="button" className="btn btn-ghost" onClick={() => void i18n.changeLanguage('en')}>{t('lang.en')}</button>
        </div>
      </form>
    </div>
  );
}
