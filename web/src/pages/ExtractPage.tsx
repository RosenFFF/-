import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted } from "../api/http";
import { poll } from "../api/poll";
import type {
  Document,
  Recognition,
  Location,
  ExtractedField,
} from "../api/types";
import { DocPreview } from "../components/DocPreview";
import { ErrorNotice } from "../components/ErrorNotice";
export function ExtractPage() {
  const { id } = useParams();
  const [query] = useSearchParams();
  return <ExtractContent key={`${id}:${query.toString()}`} />;
}
function ExtractContent() {
  const { id = "" } = useParams();
  const [query] = useSearchParams();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [doc, setDoc] = useState<Document | null>(null);
  const [result, setResult] = useState<Recognition | null>(null);
  const [selected, setSelected] = useState("");
  const [edit, setEdit] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  const focusField = query.get("field") ?? "";
  const focusBlock = query.get("block") ?? "";
  useEffect(() => {
    const c = new AbortController();
    void (async () => {
      const d = await poll(
        () => api.document(id, c.signal),
        "ready",
        c.signal,
        setDoc,
      );
      const recognition = await api.recognition(d.id, c.signal);
      if (c.signal.aborted) return;
      setResult(recognition);
      const field =
        recognition.fields.find((f) => f.key === focusField) ??
        recognition.fields[0];
      const block = recognition.ocr.blocks.find((b) => b.id === focusBlock);
      setSelected(block?.id ?? field?.key ?? "");
      setEdit(field?.value ?? "");
      const location = block ?? field?.locations?.[0];
      if (location) setPage(location.page);
    })().catch((e: unknown) => {
      if (!aborted(e)) setError(e);
    });
    return () => c.abort();
  }, [id, retry, focusField, focusBlock]);
  const field = result?.fields.find((f) => f.key === selected);
  const locations = useMemo<Location[]>(() => {
    if (!result) return [];
    const block = result.ocr.blocks.find(
      (b) => b.id === selected || (!selected && b.id === focusBlock),
    );
    if (block) return [block];
    return field?.locations?.length
      ? field.locations
      : result.ocr.blocks.filter((b) =>
          field?.source_block_ids?.includes(b.id),
        );
  }, [field, result, selected, focusBlock]);
  function selectField(f: ExtractedField) {
    setSelected(f.key);
    setEdit(f.value ?? "");
    const loc =
      f.locations?.[0] ??
      result?.ocr.blocks.find((b) => f.source_block_ids?.includes(b.id));
    if (loc) setPage(loc.page);
  }
  async function save() {
    if (!result || !field) return;
    setSaving(true);
    setError(null);
    try {
      setResult(
        await api.patchFields(id, result.version, [
          { key: field.key, value: edit },
        ]),
      );
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">{t("extract.title")}</h1>
          <div>{doc?.filename}</div>
          <p className="muted">{t("extract.hint")}</p>
        </div>
        {result ? (
          <Link className="btn" to={`/cases/${id}/report`}>
            {t("extract.continue")}
          </Link>
        ) : null}
      </div>
      <ErrorNotice error={error} />
      {error ? (
        <button
          className="btn btn-secondary"
          onClick={() => {
            setError(null);
            setResult(null);
            setDoc(null);
            setRetry((v) => v + 1);
          }}
        >
          {t("common.retry")}
        </button>
      ) : null}
      {!result && !error ? (
        <div role="status">
          {t(doc ? `documentStatus.${doc.status}` : "status.running")} ·{" "}
          {doc?.progress ?? 0}%
        </div>
      ) : null}
      {result ? (
        <div className="grid-2">
          <DocPreview
            documentId={id}
            page={page}
            pages={doc?.pages ?? 1}
            onPage={setPage}
            highlights={locations}
          />
          <div className="stack result-column">
            {!result.fields.length ? (
              <div className="banner">{t("extract.noFields")}</div>
            ) : (
              <div className="panel table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t("extract.fields")}</th>
                      <th>{t("common.value")}</th>
                      <th>{t("extract.confidence")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.fields.map((f) => (
                      <tr
                        key={f.key}
                        className={selected === f.key ? "selected" : ""}
                      >
                        <td>
                          <button
                            className="btn btn-ghost field-button"
                            onClick={() => selectField(f)}
                          >
                            {f.label}
                          </button>
                        </td>
                        <td className="mono">{f.value ?? "—"}</td>
                        <td>
                          {f.confidence == null ? (
                            "—"
                          ) : (
                            <span
                              className={
                                f.confidence < 0.8 ? "badge badge-med" : "badge"
                              }
                            >
                              {Math.round(f.confidence * 100)}%
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {field ? (
              <div className="panel form-panel">
                <label>
                  {field.label}
                  <input
                    className="input"
                    value={edit}
                    onChange={(e) => setEdit(e.target.value)}
                    maxLength={2000}
                  />
                </label>
                <button
                  className="btn btn-secondary"
                  disabled={saving || edit === field.value}
                  onClick={() => void save()}
                >
                  {t("extract.save")}
                </button>
              </div>
            ) : null}
            <div className="panel">
              <h2 className="section-title">
                {t("extract.ocrText")} · {result.ocr.engine}
              </h2>
              {!result.ocr.blocks.length ? (
                <p>{t("common.empty")}</p>
              ) : (
                <ul className="ocr-blocks">
                  {result.ocr.blocks.map((b) => (
                    <li key={b.id}>
                      <button
                        className="btn btn-ghost"
                        onClick={() => {
                          setSelected(b.id);
                          setPage(b.page);
                        }}
                      >
                        {t("extract.page")} {b.page} · {b.text}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
