# 前端对齐后端 degrade_status / 引用来源（8d94e02）

日期：2026-11-05（America/Tijuana）。分支 `feat/frontend-m1-api`，前端 HEAD `398f619`，基线 `d3c0b09`。联调后端 `8d94e02`。仅本地前端 worktree + bundle，不推远程。

## 改动范围

- 报告/识别级：渲染接口返回的 `degrade_status` 原文 + `llm_verified`；缺字段显示「状态信息缺失」，不再用前端固定 L0–L3 文案顶替
- 引用与规则详情：`source_kind` / `source_kind_label` / `url` / `article` / `version_date` / `excerpt_kind` / `applicability`；公开摘要明示非法规原文、非完整适用证据；缺失「来源信息缺失」
- 同步 `docs/api.yaml`；mock / e2e / 真实 HTTPS 截图脚本

## 检查结果

- build / oxlint / vitest 76 / mock e2e 2（390+1440）通过
- 真实联调（Vite HTTPS 代理 → 本地 8d94e02 fixture）：缺 CSRF / 伪造 CSRF / 跨 Origin 写操作 403；上传+OCR；审查 L3；规则详情带来源字段；追问 messages GET/POST 501 → 「功能暂未实现」、不回退 mock
- 真实截图无 MOCK 红条：`/workspace/competition/screenshots/m1/real-{login,upload,extract,report,ask-501}-{390,1440}.png`（共 10 张）
- npm audit 0；`scripts/security-scan.sh` CRITICAL/HIGH/MEDIUM/LOW=0
- bundle：`/workspace/competition/bundles/feat-frontend-m1-api.bundle`（`d3c0b09..feat/frontend-m1-api`，list-heads 含分支名）

## 仍待后端

1. 追问/SSE：`/reviews/{id}/messages` GET/POST 仍 501（模型下载受阻，未绕过）
2. 合成引用 `url`/`version_date` 常为 null——前端如实显示缺失；公开语料需持续带齐可核验元数据
3. 真实 LLM 可用后才有非 L3 `degrade_status` 联调证据
