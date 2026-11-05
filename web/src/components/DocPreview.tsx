import type { BBox } from '../mock/types';

type Props = {
  page: number;
  pages: number;
  onPage: (p: number) => void;
  highlight?: { page: number; bbox: BBox } | null;
  pageLabel: string;
};

/** Mock multi-page document surface with normalized bbox overlay. */
export function DocPreview({ page, pages, onPage, highlight, pageLabel }: Props) {
  const show = highlight && highlight.page === page ? highlight.bbox : null;
  return (
    <div className="panel" style={{ padding: 12, display: 'grid', gap: 12, height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <button type="button" className="btn btn-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          ‹
        </button>
        <span className="mono muted">
          {pageLabel} {page} / {pages}
        </span>
        <button type="button" className="btn btn-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          ›
        </button>
      </div>
      <div
        className="doc-page"
        style={{
          position: 'relative',
          flex: 1,
          minHeight: 420,
          background: page === 1 ? '#fbfcfd' : '#f7f8fa',
          border: '1px solid var(--line)',
          borderRadius: 4,
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: 24, color: 'var(--ink-secondary)', fontSize: 13 }}>
          <div style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: 12 }}>
            {page === 1 ? 'COMMERCIAL INVOICE · INV-2026-8841' : 'PACKING LIST · PL-2026-8841'}
          </div>
          <div className="muted">Mock page content for demo highlighting (not a scanned image).</div>
          <div style={{ marginTop: 24, height: 1, background: 'var(--line)' }} />
          <div style={{ marginTop: 16 }} className="mono">
            Shipper / Consignee / Totals …
          </div>
        </div>
        {show ? (
          <div
            aria-hidden
            style={{
              position: 'absolute',
              left: `${show.x * 100}%`,
              top: `${show.y * 100}%`,
              width: `${show.w * 100}%`,
              height: `${show.h * 100}%`,
              border: '2px solid var(--brand)',
              background: 'rgba(15, 92, 92, 0.12)',
              borderRadius: 2,
              pointerEvents: 'none',
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
