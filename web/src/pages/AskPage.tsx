import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, useMock } from "../api";
import { aborted, ApiError } from "../api/http";
import { askStream } from "../api/real";
import { chatProvenance } from "../api/degradeStatus";
import type { Language, ChatMessage } from "../api/types";
import { languages } from "../api/languages";
import { ErrorNotice } from "../components/ErrorNotice";
import { DegradeStrip } from "../components/DegradeStrip";
import { CitationSource } from "../components/Provenance";
import { FlowTrail } from "../components/FlowTrail";

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
  const [liveMessageId, setLiveMessageId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const controller = useRef<AbortController | null>(null);
  const liveRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    if (reconnecting) liveRef.current?.focus();
  }, [reconnecting]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const content = input.trim();
    if (!content || busy || !reviewId || !historyLoaded) return;
    const replyId = crypto.randomUUID();
    const userId = crypto.randomUUID();
    const stamp = new Date().toISOString();
    setInput("");
    setBusy(true);
    setError(null);
    setReconnecting(false);
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
    setLiveMessageId(replyId);
    setMessages((m) => [...m, user, reply]);
    const applyReply = (snapshot: ChatMessage) => {
      reply = snapshot;
      setMessages((m) =>
        m.map((v) =>
          v.id === replyId || v.id === snapshot.id ? snapshot : v,
        ),
      );
    };
    try {
      const stream = useMock
        ? api.ask(reviewId, content, lang, signal)
        : askStream(reviewId, content, lang, {
            signal,
            onResume: () => setReconnecting(true),
          });
      for await (const ev of stream) {
        setReconnecting(false);
        if (ev.event === "error") throw new ApiError(ev.data);
        if (ev.event === "delta")
          applyReply({ ...reply, content: reply.content + ev.data.text });
        if (ev.event === "citation")
          applyReply({
            ...reply,
            citations: [...(reply.citations ?? []), ev.data],
          });
        if (ev.event === "done") {
          setLiveMessageId(ev.data.id);
          applyReply(ev.data);
        }
      }
    } catch (err) {
      if (!aborted(err)) {
        // Resume already attempted inside askStream. On 404/interrupt, reload history once — never invent a new POST.
        try {
          const history = await api.messages(reviewId, signal);
          setMessages(history.items);
        } catch (historyError) {
          if (!aborted(historyError) && !signal.aborted) {
            /* keep primary error */
          }
        }
        if (!signal.aborted) setError(err);
      }
    } finally {
      setBusy(false);
      setReconnecting(false);
    }
  }

  return (
    <div className="stack ask-page">
      <FlowTrail />
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
        <div
          className="banner ask-reconnect"
          role="status"
          aria-live="polite"
          tabIndex={-1}
          ref={liveRef}
        >
          {t("ask.reconnecting")}
        </div>
      ) : null}
      <div className="panel chat-history">
        {!historyLoaded && reviewId ? (
          <p className="muted" role="status">
            {t("ask.historyLoading")}
          </p>
        ) : null}
        {historyLoaded && messages.length === 0 && reviewId ? (
          <p className="muted" role="status">
            {t("ask.historyEmpty")}
          </p>
        ) : null}
        {messages.map((m) => {
          const provenance = chatProvenance(m);
          return (
            <div
              key={m.id}
              className={`chat-message ${m.role}${m.blocked ? " blocked" : ""}`}
            >
              <div aria-live={m.id === liveMessageId ? "polite" : undefined}>
                {m.blocked
                  ? t("ask.jailbreakBlocked")
                  : m.content || (busy ? t("status.running") : "")}
              </div>
              {provenance ? <DegradeStrip view={provenance} live={false} /> : null}
              {m.blocked && m.block_reason ? (
                <p className="muted">
                  {t("ask.blockReason")}: {t(`ask.blockReason.${m.block_reason}`)}
                </p>
              ) : null}
              {m.citations?.map((c, i) => (
                <div key={`${c.rule_id}-${i}`} className="chat-citation">
                  <CitationSource value={c} />
                  <blockquote className="serif citation">
                    <span className="citation-body">
                      {c.source} · {c.article}: {c.excerpt}
                    </span>
                  </blockquote>
                </div>
              ))}
              {m.aigc ? <p className="muted">{m.aigc.explicit_text}</p> : null}
            </div>
          );
        })}
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
