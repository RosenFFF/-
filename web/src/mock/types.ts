export type Role = 'reviewer' | 'admin' | 'auditor';

export type AnswerLang = 'zh' | 'en' | 'ru' | 'vi' | 'pt' | 'ar';

export type BBox = { x: number; y: number; w: number; h: number };

export type FieldLocation = { page: number; bbox: BBox };

export type ExtractedField = {
  id: string;
  key: string;
  label: string;
  value: string;
  confidence: number;
  locations: FieldLocation[];
  source_block_ids: string[];
};

export type RiskLevel = 'high' | 'medium' | 'low' | 'pass';

export type Finding = {
  id: string;
  level: RiskLevel;
  title: string;
  detail: string;
  rule_id: string;
  citation: string;
  field_ids: string[];
};

export type AuditEvent = {
  id: string;
  at: string;
  actor: string;
  action: string;
  detail: string;
  outcome: 'ok' | 'denied' | 'blocked';
  caseId?: string;
};

export type ModelCall = {
  id: string;
  stage: string;
  model: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
};

export type CaseRecord = {
  id: string;
  title: string;
  docType: string;
  status: 'uploaded' | 'extracting' | 'ready' | 'reviewing' | 'done';
  pages: number;
  offline?: boolean;
};
