import { useTranslation } from 'react-i18next';
import { getModelCalls, getSystemModels } from '../mock/api';

export function ModelsPage() {
  const { t } = useTranslation();
  const models = getSystemModels();
  const calls = getModelCalls();
  return (
    <div className="stack">
      <h1 className="page-title">{t('models.title')}</h1>
      <div className="panel" style={{ overflow: 'auto' }}>
        <table className="table">
          <thead>
            <tr><th>Kind</th><th>Name</th><th>Deploy</th><th>Status</th></tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={`${m.kind}-${m.name}`}>
                <td>{m.kind}</td>
                <td className="mono">{m.name}</td>
                <td>{m.deploy}</td>
                <td>{m.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel" style={{ overflow: 'auto' }}>
        <table className="table">
          <thead>
            <tr><th>Stage</th><th>Model</th><th>Latency</th><th>Tokens</th></tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id}>
                <td>{c.stage}</td>
                <td className="mono">{c.model}</td>
                <td className="mono">{c.latency_ms} ms</td>
                <td className="mono">{c.tokens_in} / {c.tokens_out}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
