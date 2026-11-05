import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { pollReview, startReview } from '../mock/api';
import type { AnswerLang, Finding } from '../mock/types';
import { MODEL_CALLS } from '../mock/data';

function badgeClass(level: Finding['level']) {
  if (level === 'high') return 'badge badge-high';
  if (level === 'medium') return 'badge badge-med';
  if (level === 'low') return 'badge badge-low';
  return 'badge badge-pass';
}

export function ReportPage() {
  const { t } = useTranslation();
  const [lang, setLang] = useState<AnswerLang>('ru');
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [active, setActive] = useState<Finding | null>(null);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  async function run() {
    setBusy(true);
    try {
      await startReview(lang);
      const res = await pollReview();
      setFindings(res.findings);
      setActive(res.findings[0] ?? null);
      setOffline(Boolean(res.offline));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="stack">
      <div className="page-head">
        <h1 className="page-title" style={{ margin: 0 }}>{t('report.title')}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
            <span className="muted">{t('report.answerLang')}</span>
            <select className="select" style={{ width: 'auto' }} value={lang} onChange={(e) => setLang(e.target.value as AnswerLang)}>
              {(['zh', 'en', 'ru', 'vi', 'pt', 'ar'] as AnswerLang[]).map((l) => (
                <option key={l} value={l}>{t(`answer.${l}`)}</option>
              ))}
            </select>
          </label>
          <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => void run()}>
            {busy ? t('status.running') : t('extract.continue')}
          </button>
          <Link className="btn" to="/cases/case_demo_001/ask">{t('report.ask')}</Link>
        </div>
      </div>
      {offline ? <div className="banner">{t('report.offline')}</div> : null}
      <div className="banner" style={{ background: 'var(--brand-subtle)', color: 'var(--brand)' }}>{t('report.aigc')}</div>
      <div className="grid-2">
        <div className="panel" style={{ overflow: 'auto' }}>
          <div style={{ padding: 12, fontWeight: 600 }}>{t('report.riskSummary')}</div>
          <table className="table">
            <tbody>
              {(findings ?? []).map((f) => (
                <tr key={f.id} className={`clickable${active?.id === f.id ? ' selected' : ''}`} onClick={() => setActive(f)}>
                  <td><span className={badgeClass(f.level)}>{f.level}</span></td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{f.title}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{f.detail}</div>
                  </td>
                  <td className="mono muted">{f.rule_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel" style={{ padding: 16, display: 'grid', gap: 12, alignContent: 'start' }}>
          <div style={{ fontWeight: 600 }}>{t('report.citations')}</div>
          {active ? (
            <>
              <div className="mono muted">{active.rule_id}</div>
              <blockquote className="serif" style={{ margin: 0, padding: 12, background: 'var(--canvas)', borderLeft: '3px solid var(--brand)' }}>
                {active.citation}
              </blockquote>
              <div className="muted" style={{ fontSize: 13 }}>{active.detail}</div>
            </>
          ) : (
            <div className="muted">{t('status.running')}</div>
          )}
          <div style={{ marginTop: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>model_calls</div>
            <table className="table">
              <thead>
                <tr><th>Stage</th><th>Model</th><th>ms</th><th>tok</th></tr>
              </thead>
              <tbody>
                {MODEL_CALLS.map((m) => (
                  <tr key={m.id}>
                    <td>{m.stage}</td>
                    <td className="mono">{m.model}</td>
                    <td className="mono">{m.latency_ms}</td>
                    <td className="mono">{m.tokens_in}/{m.tokens_out}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
