import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { askStream } from '../mock/api';
import type { AnswerLang } from '../mock/types';

type Msg = { role: 'user' | 'assistant' | 'system'; text: string; citation?: string };

export function AskPage() {
  const { t } = useTranslation();
  const [lang, setLang] = useState<AnswerLang>('ru');
  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);

  async function send(e: FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || busy) return;
    setInput('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    let assistant = '';
    let citation = '';
    setMsgs((m) => [...m, { role: 'assistant', text: '' }]);
    try {
      for await (const ev of askStream(q, lang)) {
        if (ev.event === 'delta') {
          assistant += ev.text;
          const snap = assistant;
          setMsgs((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: 'assistant', text: snap, citation };
            return copy;
          });
        } else if (ev.event === 'citation') {
          citation = `${ev.rule_id}: ${ev.text}`;
          setMsgs((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: 'assistant', text: assistant, citation };
            return copy;
          });
        } else if (ev.event === 'error') {
          setMsgs((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: 'system', text: t('ask.jailbreakBlocked') };
            return copy;
          });
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 860 }}>
      <div className="page-head">
        <h1 className="page-title" style={{ margin: 0 }}>{t('ask.title')}</h1>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
          <span className="muted">{t('report.answerLang')}</span>
          <select className="select" style={{ width: 'auto' }} value={lang} onChange={(e) => setLang(e.target.value as AnswerLang)}>
            {(['zh', 'en', 'ru', 'vi', 'pt', 'ar'] as AnswerLang[]).map((l) => (
              <option key={l} value={l}>{t(`answer.${l}`)}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="panel" style={{ padding: 16, minHeight: 360, display: 'grid', gap: 12 }}>
        {msgs.map((m, i) => (
          <div key={i} style={{ justifySelf: m.role === 'user' ? 'end' : 'start', maxWidth: '85%' }}>
            <div
              style={{
                padding: '10px 12px',
                borderRadius: 6,
                border: '1px solid var(--line)',
                background: m.role === 'user' ? 'var(--brand-subtle)' : m.role === 'system' ? '#fef3f2' : 'var(--paper)',
              }}
            >
              {m.text}
            </div>
            {m.citation ? (
              <blockquote className="serif" style={{ margin: '8px 0 0', padding: 10, background: 'var(--canvas)', borderLeft: '3px solid var(--brand)', fontSize: 13 }}>
                {m.citation}
              </blockquote>
            ) : null}
          </div>
        ))}
      </div>
      <form onSubmit={send} style={{ display: 'flex', gap: 8 }}>
        <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t('ask.placeholder')} />
        <button className="btn" type="submit" disabled={busy}>{t('ask.send')}</button>
      </form>
    </div>
  );
}
