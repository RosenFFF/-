import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted } from "../api/http";
import type { Document } from "../api/types";
import { ErrorNotice } from "../components/ErrorNotice";
export function CasesPage() {
  const { t } = useTranslation();
  const [docs, setDocs] = useState<Document[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    void api
      .listDocuments(c.signal)
      .then((r) => setDocs(r.items))
      .catch((e: unknown) => {
        if (!aborted(e)) setError(e);
      });
    return () => c.abort();
  }, [retry]);
  return (
    <div className="stack">
      <div className="page-head">
        <h1 className="page-title">{t("cases.title")}</h1>
        <Link className="btn" to="/cases/new">
          {t("cases.new")}
        </Link>
      </div>
      <ErrorNotice error={error} />
      {error ? (
        <button
          className="btn btn-secondary"
          onClick={() => {
            setError(null);
            setDocs(null);
            setRetry((v) => v + 1);
          }}
        >
          {t("common.retry")}
        </button>
      ) : null}
      {!docs && !error ? <div role="status">{t("status.running")}</div> : null}
      {docs?.length === 0 ? <p>{t("cases.empty")}</p> : null}
      {docs?.length ? (
        <div className="panel table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("common.filename")}</th>
                <th>{t("upload.type")}</th>
                <th>{t("common.status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    {doc.filename}
                    <div className="mono muted">{doc.id}</div>
                  </td>
                  <td>{t(`docType.${doc.doc_type}`)}</td>
                  <td>{t(`documentStatus.${doc.status}`)}</td>
                  <td>
                    <Link to={`/cases/${doc.id}/extract`}>
                      {t("nav.extract")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
