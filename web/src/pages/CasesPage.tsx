import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { listCases } from '../mock/api';
import type { CaseRecord } from '../mock/types';

export function CasesPage() {
  const { t } = useTranslation();
  const [cases, setCases] = useState<CaseRecord[] | null>(null);

  useEffect(() => {
    void listCases().then(setCases);
  }, []);

  if (!cases) return <div className="muted">{t('status.running')}</div>;
  if (!cases.length) {
    return (
      <div className="stack">
        <h1 className="page-title">{t('cases.title')}</h1>
        <div className="panel" style={{ padding: 24 }}>
          <p>{t('cases.empty')}</p>
          <Link className="btn" to="/cases/new">{t('cases.new')}</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1 className="page-title" style={{ margin: 0 }}>{t('cases.title')}</h1>
        <Link className="btn" to="/cases/new">{t('nav.upload')}</Link>
      </div>
      <div className="panel" style={{ overflow: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Type</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id}>
                <td className="mono">{c.id}</td>
                <td>{c.title}</td>
                <td>{c.docType}</td>
                <td>{c.status}</td>
                <td><Link to={`/cases/${c.id}/extract`}>{t('nav.extract')}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
