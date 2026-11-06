import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted, ApiError } from "../api/http";
import type { DocType, Document } from "../api/types";
import { poll } from "../api/poll";
import { ErrorNotice } from "../components/ErrorNotice";
import { FlowTrail } from "../components/FlowTrail";
export function UploadPage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [docType, setDocType] = useState<DocType>("commercial_invoice");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState<Document | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function start() {
    if (!file || busy) return;
    if (file.size > 10 * 1024 * 1024) {
      setError(new ApiError({ code: "FILE_TOO_LARGE", status: 413 }));
      return;
    }
    setBusy(true);
    setError(null);
    controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      const doc = progress?.id
        ? progress
        : await api.upload(file, docType, signal);
      setProgress(doc);
      await poll(
        () => api.document(doc.id, signal),
        "ready",
        signal,
        setProgress,
      );
      nav(`/cases/${doc.id}/extract`);
    } catch (err) {
      if (!aborted(err)) setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <FlowTrail />
      <h1 className="page-title">{t("upload.title")}</h1>
      <ErrorNotice error={error} />
      <div className="panel form-panel">
        <label>
          {t("upload.type")}
          <select
            className="select"
            value={docType}
            disabled={busy || !!progress}
            onChange={(e) => setDocType(e.target.value as DocType)}
          >
            {(
              [
                "commercial_invoice",
                "packing_list",
                "certificate_of_origin",
                "customs_declaration",
                "bill_of_lading",
                "unknown",
              ] as DocType[]
            ).map((type) => (
              <option key={type} value={type}>
                {t(`docType.${type}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={file ? "file-picker has-file" : "file-picker"}>
          {t("upload.drop")}
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            disabled={busy || !!progress}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
          />
          {file ? (
            <span className="muted" role="status">
              {t("upload.fileChosen")}: {file.name}
            </span>
          ) : null}
        </label>
        <div className="muted">{t("upload.privacy")}</div>
        {progress ? (
          <div role="status">
            {t(`documentStatus.${progress.status}`)} · {progress.progress ?? 0}%
            <progress max={100} value={progress.progress ?? 0} />
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => nav(`/cases/${progress.id}/extract`)}
            >
              {t("nav.extract")}
            </button>
          </div>
        ) : null}
        <div className="action-row">
          <button
            className="btn"
            type="button"
            disabled={busy || !file || progress?.status === "failed"}
            onClick={() => void start()}
          >
            {busy
              ? t("status.running")
              : progress
                ? t("common.retry")
                : t("upload.start")}
          </button>
          {busy ? (
            <button
              className="btn btn-secondary"
              onClick={() => controller.current?.abort()}
            >
              {t("common.cancelWait")}
            </button>
          ) : null}
          {progress && !busy ? (
            <button
              className="btn btn-secondary"
              onClick={() => {
                setProgress(null);
                setFile(null);
                setError(null);
              }}
            >
              {t("cases.new")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
