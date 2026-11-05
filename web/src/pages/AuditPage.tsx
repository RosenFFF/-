import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';
import { getCaseAudit, getGlobalAudit, verifyAuditChain } from '../mock/api';
import type { AuditEvent } from '../mock/types';

export function AuditPage() {
  const { t } = useTranslation();
  const { role } = useAuth();
  const [own, setOwn] = useState<AuditEvent[] | null>(null);
  const [globalErr, setGlobalErr] = useState('');
  const [global, setGlobal] = useState<Awaited<ReturnType<typeof getGlobalAudit>> | null>(null);
  const [verify, setVerify] = useState('');

  async function loadOwn() {
    setOwn(await getCaseAudit());
  }

  async function loadGlobal() {
    setGlobalErr('');
    setGlobal(null);
    try {
      setGlobal(await getGlobalAudit(role ?? 'reviewer'));
    } catch (e) {
      const err = e as { code?: string };
      setGlobalErr(err.code === 'FORBIDDEN' ? t('audit.forbidden') : 'error');
    }
  }

  async function onVerify() {
    const res = await verifyAuditChain();
    setVerify(res.ok ? t('audit.verified') : `broken at ${res.broken_at}`);
  }

  return (
    <div className="stack">
      <h1 className="page-title">{t('audit.title')}</h1>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button className="btn btn-secondary" type="button" onClick={() => void loadOwn()}>{t('audit.own')}</button>
        <button className="btn btn-secondary" type="button" onClick={() => void loadGlobal()}>{t('audit.global')}</button>
        <button className="btn" type="button" onClick={() => void onVerify()}>{t('audit.verify')}</button>
      </div>
      {verify ? <div className="banner" style={{ background: 'var(--brand-subtle)', color: 'var(--brand)' }}>{verify}</div> : null}
      {globalErr ? <div className="banner" style={{ background: '#fef3f2', color: 'var(--risk-high)' }}>{globalErr}</div> : null}
      {own ? (
        <div className="panel" style={{ overflow: 'auto' }}>
          <table className="table">
            <thead>
              <tr><th>Time</th><th>Actor</th><th>Action</th><th>Outcome</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {own.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{e.at}</td>
                  <td>{e.actor}</td>
                  <td className="mono">{e.action}</td>
                  <td>{e.outcome}</td>
                  <td>{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {global ? (
        <div className="stack">
          <div className="panel" style={{ padding: 16, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div><div className="muted">logins</div><div className="mono" style={{ fontSize: 24 }}>{global.stats.logins}</div></div>
            <div><div className="muted">denials</div><div className="mono" style={{ fontSize: 24 }}>{global.stats.denials}</div></div>
            <div><div className="muted">blocks</div><div className="mono" style={{ fontSize: 24 }}>{global.stats.blocks}</div></div>
            <div><div className="muted">model_calls</div><div className="mono" style={{ fontSize: 24 }}>{global.stats.model_calls}</div></div>
          </div>
          <div className="panel" style={{ padding: 16 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>redaction preview</div>
            <div className="mono" style={{ fontSize: 13 }}><strong>in:</strong> {global.redaction.original}</div>
            <div className="mono" style={{ fontSize: 13, marginTop: 8 }}><strong>out:</strong> {global.redaction.redacted}</div>
          </div>
          <div className="panel" style={{ overflow: 'auto' }}>
            <table className="table">
              <thead>
                <tr><th>Time</th><th>Actor</th><th>Action</th><th>Outcome</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {global.logs.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{e.at}</td>
                    <td>{e.actor}</td>
                    <td className="mono">{e.action}</td>
                    <td>{e.outcome}</td>
                    <td>{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
