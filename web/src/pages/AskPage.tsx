import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { aborted, ApiError } from "../api/http";
import { wait } from "../api/poll";
import type { Language, ChatMessage } from "../api/types";
import { languages } from "../api/languages";
import { ErrorNotice } from "../components/ErrorNotice";
import { CitationSource } from "../components/Provenance";
export function AskPage() {
  const [query] = useSearchParams();
  return <AskContent key={query.get("review") ?? ""} />;
}
function AskContent() {
  const { id = "" } = useParams();
  const [query] = useSearchParams();
  const reviewId = query.get("review") ?? "";
  const { t } = useTranslation();
  const [lang, setLang] = useState<Language>("zh-CN");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const c = new AbortController();
    if (reviewId)
      void api
        .messages(reviewId, c.signal)
        .then((r) => {
          setMessages(r.items);
          setHistoryLoaded(true);
        })
        .catch((e: unknown) => {
          if (!aborted(e)) setError(e);
        });
    return () => {
      c.abort();
      controller.current?.abort();
    };
  }, [reviewId]);
  async function send(e: FormEvent) {
    e.preventDefault();
    const content = input.trim();
    if (!content || busy || !reviewId || !historyLoaded) return;
    const baseline = new Set(messages.map((m) => m.id));
    const replyId = crypto.randomUUID();
    const userId = crypto.randomUUID();
    const stamp = new Date().toISOString();
    setInput("");
    setBusy(true);
    setError(null);
    controller.current = new AbortController();
    const signal = controller.current.signal;
    const user: ChatMessage = {
      id: userId,
      role: "user",
      content,
      blocked: false,
      created_at: stamp,
    };
    let reply: ChatMessage = {
      id: replyId,
      role: "assistant",
      content: "",
      blocked: false,
      created_at: stamp,
      citations: [],
    };
    setMessages((m) => [...m, user, reply]);
    try {
      for await (const ev of api.ask(reviewId, content, lang, signal)) {
        if (ev.event === "error") throw new ApiError(ev.data);
        if (ev.event === "delta")
          reply = { ...reply, content: reply.content + ev.data.text };
        if (ev.event === "citation")
          reply = {
            ...reply,
            citations: [...(reply.citations ?? []), ev.data],
          };
        if (ev.event === "done") reply = ev.data;
        const snapshot = reply;
        setMessages((m) =>
          m.map((v) =>
            v.id === replyId || v.id === snapshot.id ? snapshot : v,
          ),
        );
      }
    } catch (err) {
      if (!aborted(err)) {
        // Contract has no resume cursor / idempotency key. NEVER replay the POST.
        // Reconnect read-only history with bounded backoff; recover the persisted answer.
        const interrupted =
          err instanceof ApiError &&
          ["STREAM_INTERRUPTED", "NETWORK_ERROR"].includes(err.problem.code);
        let recovered = false;
        if (interrupted) {
          setReconnecting(true);
          for (let attempt = 0; attempt < 3; attempt++) {
            try {
              await wait(1000 * 2 ** attempt, signal);
              const history = await api.messages(reviewId, signal);
              const added = history.items.filter((m) => !baseline.has(m.id));
              const questionIndex = added.findIndex(
                (m) => m.role === "user" && m.content === content,
              );
              if (
                questionIndex >= 0 &&
                added[questionIndex + 1]?.role === "assistant"
              ) {
                setMessages(history.items);
                recovered = true;
                break;
              }
            } catch (recoveryError) {
              if (aborted(recoveryError)) break;
            }
          }
        }
        if (!recovered && !signal.aborted) setError(err);
      }
    } finally {
      setBusy(false);
      setReconnecting(false);
    }
  }
  return (
    <div className="stack" style={{ maxWidth: 900 }}>
      <div className="page-head">
        <h1 className="page-title">{t("ask.title")}</h1>
        <label>
          {t("report.answerLang")}
          <select
            className="select"
            value={lang}
            onChange={(e) => setLang(e.target.value as Language)}
          >
            {languages.map((l) => (
              <option key={l} value={l}>
                {t(`answer.${l === "zh-CN" ? "zh" : l}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!reviewId ? (
        <div className="banner">
          {t("ask.needReview")}{" "}
          <Link to={`/cases/${id}/report`}>{t("report.title")}</Link>
        </div>
      ) : null}
      <ErrorNotice error={error} />
      {reconnecting ? (
        <div className="banner" role="status">
          {t("ask.reconnecting")}
        </div>
      ) : null}
      <div className="panel chat-history" aria-live="polite">
        {messages.map((m) => (
          <div key={m.id} className={`chat-message ${m.role}`}>
            <div>{m.blocked ? t("ask.jailbreakBlocked") : m.content}</div>
            {m.citations?.map((c, i) => (
              <div key={i} className="chat-citation">
                <CitationSource value={c} />
                <blockquote className="serif citation">
                  {c.source} · {c.article}: {c.excerpt}
                </blockquote>
              </div>
            ))}
            {m.aigc ? <p className="muted">{m.aigc.explicit_text}</p> : null}
          </div>
        ))}
      </div>
      <form onSubmit={send} className="action-row">
        <input
          className="input"
          aria-label={t("ask.placeholder")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("ask.placeholder")}
          maxLength={2000}
          disabled={!reviewId || !historyLoaded || busy}
        />
        <button
          className="btn"
          type="submit"
          disabled={busy || !reviewId || !historyLoaded || !input.trim()}
        >
          {t("ask.send")}
        </button>
        {busy ? (
          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => controller.current?.abort()}
          >
            {t("common.cancelWait")}
          </button>
        ) : null}
      </form>
    </div>
  );
}
