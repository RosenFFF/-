import type { AuditEvent, CaseRecord, ExtractedField, Finding, ModelCall } from './types';

export const DEMO_CASE: CaseRecord = {
  id: 'case_demo_001',
  title: 'INV-2026-8841 · 问题样张',
  docType: 'commercial_invoice',
  status: 'ready',
  pages: 2,
};

export const FIELDS: ExtractedField[] = [
  {
    id: 'f_amount',
    key: 'total_amount',
    label: '合计金额',
    value: 'USD 128,400.00',
    confidence: 0.97,
    locations: [{ page: 1, bbox: { x: 0.62, y: 0.72, w: 0.28, h: 0.05 } }],
    source_block_ids: ['b1'],
  },
  {
    id: 'f_amount_pack',
    key: 'packing_total',
    label: '装箱单金额',
    value: 'USD 126,900.00',
    confidence: 0.93,
    locations: [{ page: 2, bbox: { x: 0.58, y: 0.68, w: 0.3, h: 0.05 } }],
    source_block_ids: ['b2'],
  },
  {
    id: 'f_hs',
    key: 'hs_code',
    label: 'HS 编码',
    value: '8471.30.00',
    confidence: 0.71,
    locations: [{ page: 1, bbox: { x: 0.12, y: 0.48, w: 0.22, h: 0.04 } }],
    source_block_ids: ['b3'],
  },
  {
    id: 'f_origin',
    key: 'origin',
    label: '原产地',
    value: 'CN',
    confidence: 0.95,
    locations: [{ page: 1, bbox: { x: 0.12, y: 0.38, w: 0.14, h: 0.04 } }],
    source_block_ids: ['b4'],
  },
  {
    id: 'f_dest',
    key: 'destination',
    label: '目的国',
    value: 'RU',
    confidence: 0.96,
    locations: [{ page: 1, bbox: { x: 0.3, y: 0.38, w: 0.14, h: 0.04 } }],
    source_block_ids: ['b5'],
  },
];

export const FINDINGS: Finding[] = [
  {
    id: 'r1',
    level: 'high',
    title: '金额不一致',
    detail: '商业发票合计与装箱单合计相差 USD 1,500.00，超出容差。',
    rule_id: 'RULE-AMT-01',
    citation: '海关总署令第 XX 号 · 单证相符审查 §3.2：发票与装箱单金额应一致，差额须书面说明。',
    field_ids: ['f_amount', 'f_amount_pack'],
  },
  {
    id: 'r2',
    level: 'medium',
    title: 'HS 编码置信度偏低',
    detail: 'OCR/抽取置信度 0.71，建议人工复核后再报关。',
    rule_id: 'RULE-HS-CONF',
    citation: '企业内部合规指引 · 低置信字段强制复核。',
    field_ids: ['f_hs'],
  },
  {
    id: 'r3',
    level: 'pass',
    title: '原产地声明可检索',
    detail: '目的国 RU 下 CN 原产地条款命中，引用已校验。',
    rule_id: 'RULE-COO-RU-12',
    citation: 'EAEU 原产地规则摘录（公开文本）§4.1：制造国声明须与装箱单一致。',
    field_ids: ['f_origin', 'f_dest'],
  },
];

export const MODEL_CALLS: ModelCall[] = [
  { id: 'm1', stage: 'OCR', model: 'RapidOCR-local', latency_ms: 1240, tokens_in: 0, tokens_out: 0 },
  { id: 'm2', stage: 'Embedding', model: 'BGE-M3-local', latency_ms: 180, tokens_in: 512, tokens_out: 0 },
  { id: 'm3', stage: 'Rerank', model: 'bge-reranker-local', latency_ms: 95, tokens_in: 0, tokens_out: 0 },
  { id: 'm4', stage: 'LLM', model: 'deepseek-chat', latency_ms: 2100, tokens_in: 1840, tokens_out: 620 },
];

export const SYSTEM_MODELS = [
  { kind: 'OCR', name: 'RapidOCR', deploy: 'local', status: 'ready' },
  { kind: 'LLM', name: 'DeepSeek (primary)', deploy: 'cloud', status: 'ready' },
  { kind: 'LLM', name: 'Qwen (failover)', deploy: 'cloud', status: 'standby' },
  { kind: 'LLM', name: 'Qwen2.5-7B', deploy: 'local', status: 'interface-only' },
  { kind: 'Embedding', name: 'BGE-M3', deploy: 'local', status: 'ready' },
  { kind: 'Reranker', name: 'bge-reranker', deploy: 'local', status: 'ready' },
];

let auditSeq = 1;
export const auditLog: AuditEvent[] = [
  {
    id: 'a0',
    at: new Date().toISOString(),
    actor: 'system',
    action: 'boot',
    detail: 'mock API ready',
    outcome: 'ok',
  },
];

export function pushAudit(e: Omit<AuditEvent, 'id' | 'at'> & { at?: string }) {
  const ev: AuditEvent = {
    id: `a${auditSeq++}`,
    at: e.at ?? new Date().toISOString(),
    actor: e.actor,
    action: e.action,
    detail: e.detail,
    outcome: e.outcome,
    caseId: e.caseId,
  };
  auditLog.unshift(ev);
  return ev;
}

export const REDACT_DEMO = {
  original: '收货人：张伟 电话：13800138000 账号：6222 **** 8899',
  redacted: '收货人：{{PERSON_1}} 电话：{{PHONE_1}} 账号：{{BANK_1}}',
};
