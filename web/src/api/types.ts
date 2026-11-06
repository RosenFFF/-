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
export type Recognition = {
  document_id: string;
  version: number;
  ocr: { engine: string; blocks: OcrBlock[] };
  fields: ExtractedField[];
  models: ModelTrace[];
  aigc?: Aigc;
};
export type Citation = {
  rule_id: string;
  source: string;
  article: string;
  excerpt: string;
  url?: string | null;
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
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  blocked: boolean;
  citations?: Citation[];
  aigc?: Aigc | null;
};
export type ChatEvent =
  | { event: "delta"; data: { text: string } }
  | { event: "citation"; data: Citation }
  | { event: "done"; data: ChatMessage }
  | { event: "error"; data: Problem };
export type Rule = {
  id: string;
  source: string;
  article: string;
  jurisdiction: string;
  title: string;
  text: string;
  url?: string | null;
};
export type AuditLog = {
  id: string;
  ts: string;
  actor_username?: string | null;
  action: string;
  result: string;
  request_id: string;
  hash: string;
  detail?: Record<string, unknown>;
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
  ): AsyncIterable<ChatEvent>;
  audit(reviewId?: string): Promise<Page<AuditLog>>;
  verifyAudit(): Promise<Verify>;
  models(signal?: AbortSignal): Promise<ModelChain>;
}
