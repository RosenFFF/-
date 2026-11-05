import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { createUpload, pollRecognition } from '../mock/api';

export function UploadPage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [docType, setDocType] = useState('commercial_invoice');
  const [fileName, setFileName] = useState('');
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    try {
      await createUpload();
      await pollRecognition();
      nav('/cases/case_demo_001/extract');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <h1 className="page-title">{t('upload.title')}</h1>
      <div className="panel" style={{ padding: 20, display: 'grid', gap: 14 }}>
        <label>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{t('upload.type')}</div>
          <select className="select" value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="commercial_invoice">Commercial Invoice</option>
            <option value="packing_list">Packing List</option>
            <option value="coo">Certificate of Origin</option>
            <option value="customs">Customs Declaration</option>
          </select>
        </label>
        <label
          className="panel"
          style={{ padding: 32, textAlign: 'center', borderStyle: 'dashed', cursor: 'pointer', background: 'var(--canvas)' }}
        >
          <input
            type="file"
            accept=".pdf,image/*"
            hidden
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? '')}
          />
          <div>{fileName || t('upload.drop')}</div>
        </label>
        <div className="muted" style={{ fontSize: 13 }}>{t('upload.privacy')}</div>
        <button className="btn" type="button" disabled={busy} onClick={() => void start()}>
          {busy ? t('status.running') : t('upload.start')}
        </button>
      </div>
    </div>
  );
}
