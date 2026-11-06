import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted } from "../api/http";
import type { Location } from "../api/types";
import { ErrorNotice } from "./ErrorNotice";
type Props = {
  documentId: string;
  page: number;
  pages: number;
  onPage: (p: number) => void;
  highlights: Location[];
};
export function DocPreview(props: Props) {
  return <PageImage key={`${props.documentId}:${props.page}`} {...props} />;
}
function PageImage({ documentId, page, pages, onPage, highlights }: Props) {
  const { t } = useTranslation();
  const [src, setSrc] = useState("");
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const c = new AbortController();
    let url = "";
    void api
      .image(documentId, page, c.signal)
      .then((blob) => {
        if (!c.signal.aborted) {
          url = URL.createObjectURL(blob);
          setSrc(url);
        }
      })
      .catch((e: unknown) => {
        if (!aborted(e)) setError(e);
      });
    return () => {
      c.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [documentId, page]);
  return (
    <section className="panel preview-panel" aria-label={t("extract.original")}>
      <div className="action-row preview-nav">
        <button
          type="button"
          className="btn btn-secondary"
          aria-label={t("common.previousPage")}
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          ‹
        </button>
        <span className="mono">
          {t("extract.page")} {page} / {pages}
        </span>
        <button
          type="button"
          className="btn btn-secondary"
          aria-label={t("common.nextPage")}
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          ›
        </button>
      </div>
      <ErrorNotice error={error} />
      {!src && !error ? <p role="status">{t("status.running")}</p> : null}
      {src ? (
        <div className="document-image">
          <img src={src} alt={`${t("extract.original")} ${page}`} />
          {highlights
            .filter((loc) => loc.page === page)
            .map(({ bbox: [x0, y0, x1, y1] }, i) => (
              <div
                data-testid="bbox-highlight"
                key={i}
                className="bbox-highlight"
                aria-hidden="true"
                style={{
                  left: `${x0 * 100}%`,
                  top: `${y0 * 100}%`,
                  width: `${(x1 - x0) * 100}%`,
                  height: `${(y1 - y0) * 100}%`,
                }}
              />
            ))}
        </div>
      ) : null}
    </section>
  );
}
