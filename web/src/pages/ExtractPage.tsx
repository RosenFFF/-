import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DocPreview } from '../components/DocPreview';
import { FIELDS } from '../mock/data';
import type { ExtractedField } from '../mock/types';

export function ExtractPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<ExtractedField | null>(FIELDS[0]);
  const highlight = useMemo(() => {
    if (!selected) return null;
    const loc = selected.locations.find((l) => l.page === page) ?? selected.locations[0];
    if (!loc) return null;
    if (loc.page !== page) return null;
    return loc;
  }, [selected, page]);

  function selectField(f: ExtractedField) {
    setSelected(f);
    const first = f.locations[0];
    if (first) setPage(first.page);
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title" style={{ margin: 0 }}>{t('extract.title')}</h1>
          <div className="muted" style={{ fontSize: 13 }}>{t('extract.hint')}</div>
        </div>
        <Link className="btn" to="/cases/case_demo_001/report">{t('extract.continue')}</Link>
      </div>
      <div className="grid-2">
        <DocPreview
          page={page}
          pages={2}
          onPage={setPage}
          highlight={highlight}
          pageLabel={t('extract.page')}
        />
        <div className="panel" style={{ overflow: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>{t('extract.fields')}</th>
                <th>Value</th>
                <th>{t('extract.confidence')}</th>
              </tr>
            </thead>
            <tbody>
              {FIELDS.map((f) => (
                <tr
                  key={f.id}
                  className={`clickable${selected?.id === f.id ? ' selected' : ''}`}
                  onClick={() => selectField(f)}
                >
                  <td>{f.label}</td>
                  <td className="mono">{f.value}</td>
                  <td>
                    <span className={f.confidence < 0.8 ? 'badge badge-med' : 'badge'}>
                      {(f.confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
