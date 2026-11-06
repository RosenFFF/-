/** Public wire types from docs/api.yaml v0.3.0. No browser-readable auth tokens. */
export type Role = "admin" | "reviewer" | "auditor";
export type Language = "zh-CN" | "en" | "ru" | "vi" | "pt" | "ar";
export type BBox = [number, number, number, number];
export type Location = { page: number; bbox: BBox };
export type Problem = {
  type?: string;
  title?: string;
  status: number;
  code: string;
  request_id?: string;
};
export type CurrentUser = {
  id: string;
  username: string;
  role: Role;
  tenant_id: string;
  permissions: string[];
  disabled: boolean;
  created_at: string;
};
export type SessionResponse = { expires_in: number; user: CurrentUser };
export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};
export type DocType =
  | "commercial_invoice"
  | "packing_list"
  | "certificate_of_origin"
  | "customs_declaration"
  | "bill_of_lading"
  | "unknown";
export type Document = {
  id: string;
  doc_type: DocType;
  filename: string;
  mime: string;
  size_bytes: number;
  pages?: number | null;
  status: "uploaded" | "ocr_running" | "extracting" | "ready" | "failed";
  progress?: number;
  error?: Problem | null;
  created_at: string;
};
export type OcrBlock = Location & {
  id: string;
  text: string;
  confidence: number;
};
export type ExtractedField = {
  key: string;
  label: string;
  value: string | null;
  confidence?: number | null;
  source: "llm" | "rule" | "manual";
  locations?: Location[];
  source_block_ids?: string[];
  masked?: boolean;
};
export type ModelTrace = {
  category: string;
  provider: string;
  model: string;
  task: string;
  latency_ms: number;
  status: string;
  tokens_in?: number | null;
  tokens_out?: number | null;
};
export type Aigc = {
  explicit_text: string;
  content_id: string;
  generator: string;
  generated_at: string;
};
export type SecurityFlags = {
  rule_corpus?: string;
  rule_corpus_label?: string | null;
  source_kind?: "synthetic" | "public" | null;
  source_kind_label?: string | null;
  retrieval_mode?: "bge" | "lightweight_hash";
  compliance_disclaimer?: string | null;
};
export type Recognition = {
  document_id: string;
  version: number;
  ocr: { engine: string; blocks: OcrBlock[] };
  fields: ExtractedField[];
  models: ModelTrace[];
  aigc?: Aigc;
  degrade_level?: "L0" | "L1" | "L2" | "L3";
  degrade_status?: string;
  llm_verified?: boolean;
  security?: SecurityFlags;
};
// Optional forward-compatible provenance fields; absent metadata is never inferred.
export type SourceMetadata = {
  source_kind?: "synthetic" | "public" | null;
  source_kind_label?: string | null;
  url?: string | null;
  article?: string | null;
  version_date?: string | null;
  excerpt_kind?: "summary" | "verbatim" | null;
  applicability?: "unverified" | null;
};
export type Citation = SourceMetadata & {
  rule_id: string;
  source: string;
  excerpt: string;
};
export type Finding = {
  id: string;
  severity: "info" | "low" | "medium" | "high";
  category: string;
  title: string;
  message: string;
  document_id?: string | null;
  field_keys?: string[];
  evidence_block_ids?: string[];
  suggestion?: string | null;
  determined_by: "rule" | "llm" | "llm_unverified";
  citations: Citation[];
};
export type Review = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  destination_country: string;
  document_ids?: string[];
  created_at: string;
  language: Language;
  findings: Finding[];
  risk_level?: string | null;
  summary?: string | null;
  progress?: { step: string; percent: number };
  degrade_level: "L0" | "L1" | "L2" | "L3";
  degrade_status?: string;
  llm_verified?: boolean;
  security?: SecurityFlags;
  models?: ModelTrace[];
  aigc?: Aigc;
  error?: Problem | null;
};
export type ReviewInput = {
  document_ids: string[];
  origin_country?: string;
  destination_country: string;
  language: Language;
};
export type BlockReason =
  | "prompt_injection"
  | "jailbreak"
  | "out_of_scope"
  | "sensitive_data";
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  blocked: boolean;
  block_reason?: BlockReason | null;
  citations?: Citation[];
  aigc?: Aigc | null;
};
/** Wire SSE chat event; id is "<stream UUID>:<n>" when the server assigns one. */
export type ChatEvent =
  | { event: "delta"; data: { text: string }; id?: string }
  | { event: "citation"; data: Citation; id?: string }
  | { event: "done"; data: ChatMessage; id?: string }
  | { event: "error"; data: Problem; id?: string };
export type Rule = SourceMetadata & {
  id: string;
  source: string;
  jurisdiction: string;
  title: string;
  text: string;
};
export type AuditLog = {
  id: string;
  ts: string;
  actor_id?: string | null;
  actor_username?: string | null;
  actor_role?: Role | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  result: string;
  ip?: string | null;
  request_id: string;
  detail?: Record<string, unknown>;
  prev_hash?: string | null;
  hash: string;
};
export type ModelChain = {
  degrade_level: string;
  models: {
    category: string;
    provider: string;
    model: string;
    deployment: string;
    stage: string;
    healthy: boolean;
  }[];
};
export type Verify = {
  valid: boolean;
  checked: number;
  head_hash: string;
  first_broken_id?: string | null;
};
export type AuditWindow = "1h" | "24h" | "7d";
export type SecurityTotals = {
  requests?: number;
  logins_failed?: number;
  access_denied?: number;
  rate_limited?: number;
  injections_blocked?: number;
  pii_masked?: number;
  model_calls?: number;
  model_fallbacks?: number;
  tokens_used?: number;
};
export type SecurityTimelineBucket = {
  bucket_start: string;
  access_denied?: number;
  injections_blocked?: number;
  rate_limited?: number;
  model_calls?: number;
};
export type SecurityStats = {
  window: string;
  totals: SecurityTotals;
  timeline?: SecurityTimelineBucket[];
  top_denied_actors?: { actor_username?: string; count?: number }[];
  audit_chain_valid?: boolean;
};
export interface Api {
  login(username: string, password: string): Promise<SessionResponse>;
  me(signal?: AbortSignal): Promise<CurrentUser>;
  logout(): Promise<void>;
  listDocuments(signal?: AbortSignal): Promise<Page<Document>>;
  upload(file: File, docType: DocType, signal?: AbortSignal): Promise<Document>;
  document(id: string, signal?: AbortSignal): Promise<Document>;
  recognition(id: string, signal?: AbortSignal): Promise<Recognition>;
  image(id: string, page: number, signal?: AbortSignal): Promise<Blob>;
  patchFields(
    id: string,
    version: number,
    fields: { key: string; value: string | null }[],
  ): Promise<Recognition>;
  startReview(input: ReviewInput, signal?: AbortSignal): Promise<Review>;
  review(id: string, language: Language, signal?: AbortSignal): Promise<Review>;
  rule(id: string, signal?: AbortSignal): Promise<Rule>;
  messages(id: string, signal?: AbortSignal): Promise<{ items: ChatMessage[] }>;
  ask(
    id: string,
    content: string,
    language: Language,
    signal?: AbortSignal,
    lastEventId?: string,
  ): AsyncIterable<ChatEvent>;
  audit(reviewId?: string): Promise<Page<AuditLog>>;
  auditStats(window?: AuditWindow, signal?: AbortSignal): Promise<SecurityStats>;
  verifyAudit(): Promise<Verify>;
  models(signal?: AbortSignal): Promise<ModelChain>;
}
