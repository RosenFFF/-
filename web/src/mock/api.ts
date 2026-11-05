import { DEMO_CASE, FIELDS, FINDINGS, MODEL_CALLS, SYSTEM_MODELS, auditLog, pushAudit, REDACT_DEMO } from './data';
import type { AnswerLang, Role } from './types';

export type Session = { token: string; username: string; role: Role };

const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

export async function login(username: string, password: string): Promise<Session> {
  await delay(300);
  if (!password) throw Object.assign(new Error('invalid'), { code: 'AUTH_INVALID' });
  const u = username.trim().toLowerCase();
  let role: Role;
  if (u === 'admin' || u === 'auditor') role = u as Role;
  else if (u === 'reviewer') role = 'reviewer';
  else throw Object.assign(new Error('invalid'), { code: 'AUTH_INVALID' });
  pushAudit({ actor: u, action: 'auth.login', detail: `role=${role}`, outcome: 'ok' });
  return { token: `mock.${u}`, username: u, role };
}

export async function listCases() {
  await delay(200);
  return [DEMO_CASE];
}

export async function createUpload() {
  await delay(500);
  pushAudit({
    actor: 'reviewer',
    action: 'document.upload',
    detail: DEMO_CASE.id,
    outcome: 'ok',
    caseId: DEMO_CASE.id,
  });
  return { document_id: 'doc_001', case_id: DEMO_CASE.id, status: 'accepted' as const };
}

export async function pollRecognition() {
  await delay(600);
  return { status: 'done' as const, pages: 2, fields: FIELDS };
}

export async function startReview(answerLang: AnswerLang) {
  await delay(400);
  pushAudit({
    actor: 'reviewer',
    action: 'review.start',
    detail: `lang=${answerLang}`,
    outcome: 'ok',
    caseId: DEMO_CASE.id,
  });
  return { review_id: 'rev_001', status: 'queued' as const };
}

export async function pollReview() {
  await delay(700);
  return {
    status: 'done' as const,
    findings: FINDINGS,
    model_calls: MODEL_CALLS,
    aigc: true,
    offline: false,
  };
}

export async function* askStream(question: string, answerLang: AnswerLang) {
  const q = question.toLowerCase();
  if (q.includes('ignore previous') || q.includes('越狱') || q.includes('jailbreak')) {
    pushAudit({
      actor: 'reviewer',
      action: 'ask.jailbreak_blocked',
      detail: question.slice(0, 80),
      outcome: 'blocked',
      caseId: DEMO_CASE.id,
    });
    yield { event: 'error' as const, code: 'PROMPT_INJECTION' };
    return;
  }
  const answers: Record<AnswerLang, string> = {
    zh: '建议核对装箱单金额并更正为与发票一致的 USD 128,400.00；HS 编码请人工复核后再报关。引用：RULE-AMT-01。',
    en: 'Align the packing-list total to the invoice USD 128,400.00 and manually verify the HS code before filing. Citation: RULE-AMT-01.',
    ru: 'Сверьте сумму в упаковочном листе с инвойсом USD 128,400.00 и перепроверьте код ТН ВЭД. Ссылка: RULE-AMT-01.',
    vi: 'Hãy chỉnh tổng tiền packing list khớp hóa đơn USD 128,400.00 và kiểm tra lại mã HS. Trích dẫn: RULE-AMT-01.',
    pt: 'Alinhe o total da packing list ao invoice USD 128,400.00 e revise o código HS. Citação: RULE-AMT-01.',
    ar: 'وحّد مبلغ قائمة التعبئة مع الفاتورة USD 128,400.00 وراجع رمز HS يدويًا. المرجع: RULE-AMT-01.',
  };
  const text = answers[answerLang] ?? answers.zh;
  for (const ch of text) {
    await delay(12);
    yield { event: 'delta' as const, text: ch };
  }
  yield {
    event: 'citation' as const,
    rule_id: 'RULE-AMT-01',
    text: FINDINGS[0].citation,
  };
  yield { event: 'done' as const };
}

export async function getCaseAudit() {
  await delay(200);
  return auditLog.filter((e) => !e.caseId || e.caseId === DEMO_CASE.id);
}

export async function getGlobalAudit(role: Role) {
  await delay(200);
  if (role === 'reviewer') {
    pushAudit({
      actor: 'reviewer',
      action: 'audit.read_all',
      detail: 'denied GET /audit/logs',
      outcome: 'denied',
    });
    const err = Object.assign(new Error('forbidden'), { code: 'FORBIDDEN', status: 403 });
    throw err;
  }
  return {
    logs: auditLog,
    stats: {
      logins: auditLog.filter((e) => e.action === 'auth.login').length,
      denials: auditLog.filter((e) => e.outcome === 'denied').length,
      blocks: auditLog.filter((e) => e.outcome === 'blocked').length,
      model_calls: MODEL_CALLS.length,
    },
    redaction: REDACT_DEMO,
  };
}

export async function verifyAuditChain() {
  await delay(250);
  return { ok: true, broken_at: null as string | null };
}

export function getSystemModels() {
  return SYSTEM_MODELS;
}

export function getModelCalls() {
  return MODEL_CALLS;
}
