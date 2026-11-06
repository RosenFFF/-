# 前端对齐后端 degrade_status / 引用来源（8d94e02）

日期：2026-11-05（America/Tijuana）。分支 `feat/frontend-m1-api`，基线 `d3c0b09`。仅本地前端 worktree + bundle，不推远程。

## 前端提交说明

对接后端契约：
- 报告/识别级：`degrade_status`（接口原文渲染，缺省显示「状态信息缺失」）、`llm_verified`
- 引用/规则详情：`source_kind` / `source_kind_label` / `url` / `article` / `version_date` / `excerpt_kind` / `applicability`
- 公开摘要旁明示非法规原文、非完整适用证据；缺失字段「来源信息缺失」，不推断
- 501「功能暂未实现」不回退 mock（单测 + 真实联调）

联调后端提交：`8d94e02`（含规则详情来源字段）。中间契约 `988eab8` 的 degrade 字段一并覆盖。

## 检查

- build / oxlint / vitest 76 / mock e2e 2（390+1440）通过
- 真实 HTTPS 联调（Vite 代理 → 本地 8d94e02 fixture）：CSRF 缺/伪造/跨域 403；上传 OCR；审查 L3；规则详情来源字段；追问 GET/POST messages 501
- 真实截图无 MOCK 红条：`/workspace/competition/screenshots/m1/real-*-{390,1440}.png`
- npm audit 0；security-scan CRITICAL/HIGH/MEDIUM/LOW=0

## 仍待后端

1. 追问/SSE：GET/POST `/reviews/{id}/messages` 当前 501（模型下载受阻，未绕过）
2. 合成引用的 `url`/`version_date` 常为 null——前端如实显示「来源信息缺失」；公开语料条目应继续带齐可核验元数据
3. 真实 LLM 链路通后才有非 L3 的 `degrade_status` 联调证据
