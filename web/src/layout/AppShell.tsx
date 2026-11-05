import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';
import './shell.css';

const links = [
  ['cases', '/cases'],
  ['upload', '/cases/new'],
  ['extract', '/cases/case_demo_001/extract'],
  ['report', '/cases/case_demo_001/report'],
  ['ask', '/cases/case_demo_001/ask'],
  ['audit', '/audit'],
  ['models', '/system/models'],
] as const;

export function AppShell() {
  const { t, i18n } = useTranslation();
  const { session, logout, role } = useAuth();
  const nav = useNavigate();

  return (
    <div className="shell">
      <aside className="shell-nav" aria-label="main">
        <div className="brand">
          <div className="brand-name">{t('app.name')}</div>
          <div className="brand-tag muted">{t('app.tagline')}</div>
        </div>
        <nav>
          {links.map(([key, to]) => (
            <NavLink key={key} to={to} className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}>
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
        <div className="nav-foot">
          <div className="muted" style={{ fontSize: 12 }}>
            {session?.username} · {role === 'reviewer' ? t('role.reviewer') : t('role.admin')}
          </div>
          <div className="lang-row">
            <button type="button" className="btn btn-ghost" onClick={() => void i18n.changeLanguage('zh')}>
              {t('lang.zh')}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => void i18n.changeLanguage('en')}>
              {t('lang.en')}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => void i18n.changeLanguage('vi')}>
              {t('lang.vi')}
            </button>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              logout();
              nav('/login');
            }}
          >
            {t('nav.logout')}
          </button>
        </div>
      </aside>
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
