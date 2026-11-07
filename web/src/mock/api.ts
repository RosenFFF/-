import { FIELDS, FINDINGS } from "./data";
import { ApiError } from "../api/http";
import { wait } from "../api/poll";
import type {
  Api,
  CurrentUser,
  Document,
  Recognition,
  Review,
  ChatMessage,
  Role,
} from "../api/types";

const stamp = () => new Date().toISOString();
const docId = "00000000-0000-4000-8000-000000000001";
const reviewId = "00000000-0000-4000-8000-000000000002";
const page = <T>(items: T[]) => ({
  items,
  total: items.length,
  page: 1,
  page_size: 20,
});
const user = (role: Role): CurrentUser => ({
  id: docId,
  username: role,
  role,
  tenant_id: docId,
  permissions: [],
  disabled: false,
  created_at: stamp(),
});
let current: CurrentUser | null = null;
let document: Document = {
  id: docId,
  doc_type: "commercial_invoice",
  filename: "MOCK-invoice.pdf",
  mime: "application/pdf",
  size_bytes: 1024,
  pages: 2,
  status: "ready",
  progress: 100,
  created_at: stamp(),
};
const messages: ChatMessage[] = [];
const recognition: Recognition = {
  document_id: docId,
  version: 1,
  models: [],
  degrade_level: "L3",
  degrade_status: "规则引擎回退，未完成真实 LLM 验证",
  llm_verified: false,
  security: {
    rule_corpus: "synthetic",
    rule_corpus_label: "合成或未核验语料（非真实合规结论）",
    source_kind: "synthetic",
    source_kind_label: "合成规则 · 非真实合规结论",
    retrieval_mode: "lightweight_hash",
    compliance_disclaimer:
      "自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。",
  },
  fields: FIELDS.map((field) => ({
    key: field.key,
    label: field.label,
    value: field.value,
    confidence: field.confidence,
    source: "rule",
    locations: field.locations.map(({ page, bbox: b }) => ({
      page,
      bbox: [b.x, b.y, b.x + b.w, b.y + b.h],
    })),
    source_block_ids: field.source_block_ids,
  })),
  ocr: {
    engine: "MOCK",
    blocks: FIELDS.map((field) => {
      const loc = field.locations[0];
      const b = loc.bbox;
      return {
        id: field.source_block_ids[0],
        page: loc.page,
        text: field.value,
        confidence: field.confidence,
        bbox: [b.x, b.y, b.x + b.w, b.y + b.h],
      };
    }),
  },
};
let review: Review = {
  id: reviewId,
  status: "completed",
  destination_country: "RU",
  document_ids: [docId],
  created_at: stamp(),
  language: "zh-CN",
  degrade_level: "L3",
  degrade_status: "规则引擎回退，未完成真实 LLM 验证",
  llm_verified: false,
  security: {
    source_kind: "synthetic",
    source_kind_label: "合成规则 · 非真实合规结论",
    rule_corpus: "synthetic",
    rule_corpus_label: "合成或未核验语料（非真实合规结论）",
    retrieval_mode: "lightweight_hash",
    compliance_disclaimer:
      "自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。",
  },
  summary: "MOCK · 开发用合规报告，不是真实审查。",
  findings: FINDINGS.map((finding) => ({
    id: finding.id,
    severity: finding.level === "pass" ? "info" : finding.level,
    title: finding.title,
    message: finding.detail,
    category: "other",
    determined_by: "rule",
    document_id: docId,
    field_keys: finding.field_ids.map(
      (f) => FIELDS.find((field) => field.id === f)?.key ?? f,
    ),
    citations: [
      {
        rule_id: finding.rule_id,
        source: "MOCK 开发规则",
        source_kind: "synthetic",
        source_kind_label: "合成规则 · 非真实合规结论",
        article: finding.rule_id,
        excerpt: finding.citation,
        excerpt_kind: "summary",
        applicability: "unverified",
      },
    ],
  })),
};
export const mockApi: Api = {
  async login(username, password) {
    if (!password || !["reviewer", "admin", "auditor"].includes(username))
      throw new ApiError({ code: "AUTH_INVALID_CREDENTIALS", status: 401 });
    current = user(username as Role);
    sessionStorage.setItem("sr_mock_user", JSON.stringify(current));
    return { expires_in: 900, user: current };
  },
  async me() {
    const saved = sessionStorage.getItem("sr_mock_user");
    try {
      current = saved ? (JSON.parse(saved) as CurrentUser) : null;
    } catch {
      current = null;
    }
    if (!current)
      throw new ApiError({ code: "AUTH_TOKEN_EXPIRED", status: 401 });
    return current;
  },
  async logout() {
    current = null;
    sessionStorage.removeItem("sr_mock_user");
  },
  async listDocuments() {
    return page([document]);
  },
  async upload(file, docType) {
    document = {
      ...document,
      filename: `MOCK · ${file.name}`,
      doc_type: docType,
      status: "uploaded",
      progress: 0,
    };
    return document;
  },
  async document(_id, signal) {
    await wait(100, signal);
    document = { ...document, status: "ready", progress: 100 };
    return document;
  },
  async recognition() {
    return recognition;
  },
  async image(_id, p) {
    const lines = recognition.ocr.blocks
      .filter((b) => b.page === p)
      .map(
        (b) =>
          `<text x="${b.bbox[0] * 700}" y="${b.bbox[1] * 900 + 22}" font-size="18">${b.text}</text>`,
      )
      .join("");
    return new Blob(
      [
        `<svg xmlns="http://www.w3.org/2000/svg" width="700" height="900"><rect width="700" height="900" fill="white"/><text x="30" y="50" font-size="22">MOCK · DEVELOPMENT ONLY · ${p}</text>${lines}</svg>`,
      ],
      { type: "image/svg+xml" },
    );
  },
  async patchFields(_id, _version, fields) {
    for (const f of fields) {
      const field = recognition.fields.find((v) => v.key === f.key);
      if (field) {
        field.value = f.value;
        field.source = "manual";
      }
    }
    recognition.version++;
    return structuredClone(recognition);
  },
  async startReview(input) {
    review = { ...review, ...input };
    return review;
  },
  async review(_id, language) {
    return { ...review, language };
  },
  async rule(id) {
    const citation = review.findings
      .flatMap((f) => f.citations)
      .find((c) => c.rule_id === id);
    return {
      id,
      source: "MOCK 开发规则",
      source_kind: citation?.source_kind,
      source_kind_label: citation?.source_kind_label,
      url: citation?.url,
      version_date: citation?.version_date,
      excerpt_kind: citation?.excerpt_kind,
      applicability: citation?.applicability,
      jurisdiction: "MOCK",
      article: citation?.article ?? id,
      title: id,
      text: citation?.excerpt ?? "",
    };
  },
  async messages() {
    return { items: [...messages] };
  },
  async *ask(_id, content, _language, signal, _lastEventId) {
    messages.push({
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: stamp(),
      blocked: false,
    });
    const blocked = /ignore previous|jailbreak|越狱/i.test(content);
    const reply: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: blocked
        ? "MOCK · 请求已拦截"
        : "MOCK · 请核对发票与装箱单金额。",
      created_at: stamp(),
      blocked,
      block_reason: blocked ? "jailbreak" : null,
      citations: blocked ? [] : review.findings[0].citations,
    };
    for (const text of reply.content) {
      await wait(15, signal);
      yield { event: "delta", data: { text } };
    }
    messages.push(reply);
    yield { event: "done", data: reply };
  },
  async audit(reviewId, _query) {
    if (!reviewId && current?.role === "reviewer")
      throw new ApiError({ code: "PERMISSION_DENIED", status: 403 });
    return page([]);
  },
  async verifyAudit() {
    if (current?.role === "reviewer")
      throw new ApiError({ code: "PERMISSION_DENIED", status: 403 });
    return { valid: true, checked: 0, head_hash: "MOCK", first_broken_id: null };
  },
  async auditStats(window = "24h") {
    if (current?.role === "reviewer")
      throw new ApiError({ code: "PERMISSION_DENIED", status: 403 });
    const now = new Date();
    const start = new Date(now.getTime() - 24 * 3600 * 1000);
    return {
      window,
      window_start: start.toISOString(),
      window_end: now.toISOString(),
      generated_at: now.toISOString(),
      degrade_status: "规则引擎回退，未完成真实 LLM 验证",
      llm_verified: false,
      source_kind: "synthetic",
      source_kind_label: "来源未核验 · 非真实模型验收",
      totals: {
        requests: 0,
        logins_failed: 0,
        access_denied: 0,
        rate_limited: 0,
        injections_blocked: 0,
        pii_masked: 0,
        model_calls: 0,
        model_fallbacks: 0,
        tokens_used: 0,
        outputs_blocked: 0,
        csrf_failed: 0,
        auth_locked: 0,
        model_errors: 0,
      },
      timeline: [],
      top_denied_actors: [],
      audit_chain_valid: true,
    };
  },
  async models() {
    // MOCK only: same shape as the live wire; LLMs unavailable, no fake health.
    return {
      degrade_level: "L3" as const,
      llm_provider_chain: ["MOCK-llm"],
      models: [
        { category: "ocr" as const, provider: "MOCK", model: "MOCK-ocr", deployment: "local" as const, stage: "MOCK", healthy: false, circuit_open: false, p95_latency_ms: null, calls_24h: 0 },
        { category: "llm" as const, provider: "MOCK", model: "MOCK-llm", deployment: "local" as const, stage: "MOCK", healthy: false, circuit_open: false, p95_latency_ms: null, calls_24h: 0 },
        { category: "embedding" as const, provider: "MOCK", model: "MOCK-embedding", deployment: "local" as const, stage: "MOCK", healthy: false, lightweight: true, retrieval_mode: "lightweight_hash" as const, implementation_mode: "lightweight_hash" as const, mode_label: "MOCK 轻量回退", circuit_open: false, p95_latency_ms: null, calls_24h: 0 },
      ],
    };
  },
};
