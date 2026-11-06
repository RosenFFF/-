# 前端 → 后端：M2 审计看板字段请求

> 前端分支 `feat/frontend-m2-audit`。仓库 `/workspace/competition/bundles/` 无 `feat-backend-m2*` bundle；`docs/api.yaml` 已有 `/audit/logs`、`/audit/stats`（SecurityStats）、`/audit/verify`。
> **不发明合同**：下列为看板骨架尚缺或需在现有 schema 上明确的字段；请在 `feat/backend-m2-security` 落地后回写 OpenAPI。

## 已接线（按现有 OpenAPI）

| 端点 | 用途 |
| --- | --- |
| `GET /audit/stats?window=1h\|24h\|7d` → `SecurityStats` | 指标卡 + 时间线骨架 |
| `GET /audit/logs` / `GET /reviews/{id}/audit` → `Page[AuditLog]` | 日志表 |
| `GET /audit/verify` → `Verify` | 哈希链校验 |

## 请求补充（后端尚未保证或未在 AuditLog/SecurityStats 明示）

### A. `SecurityStats` / `GET /audit/stats`

1. `window_start` / `window_end`（ISO-8601）：当前窗口起止，便于与本地时区对照。
2. `generated_at`（ISO-8601）：快照生成时间。
3. `totals.csrf_failed`（integer）：CSRF 失败次数（与登录失败分列）。
4. `totals.auth_locked`（integer）：账号锁定次数。
5. `totals.model_errors`（integer）：模型调用硬失败（非 fallback）。
6. `timeline[].logins_failed` / `pii_masked` / `model_fallbacks`：时间桶补齐与 totals 对齐的序列。
7. `degrade_status`（string \| null）：看板级降级说明（wire text，前端不编造）。
8. `llm_verified`（boolean）：本窗口统计是否经真实模型侧核对；`false` 时前端显示回退标记。
9. `source_kind` / `source_kind_label`（可选）：若统计来自合成/演示数据，必须带出处标签（与审查报告同源约定）。
10. `501 NOT_IMPLEMENTED` / `503 MODEL_UNAVAILABLE`（或 `SERVICE_UNAVAILABLE`）：端点未就绪时诚实状态码；勿返回空成功冒充已实现。

### B. `AuditLog` 条目（日志行内 provenance / fallback）

1. `detail.source_kind` / `detail.source_kind_label`（string）：单条审计关联的规则/引用出处。
2. `detail.degrade_status`（string \| null）：该次动作的降级说明。
3. `detail.llm_verified`（boolean）：该次模型相关动作是否完成真实 LLM 验证。
4. `detail.fallback_reason`（string \| null）：模型回退原因码（若 `action` 含 model/fallback）。
5. `detail.injection_category`（string \| null）：注入拦截类别（prompt / sql / path 等，枚举请后端定）。
6. `detail.pii_fields`（string[] \| null）：本条脱敏字段名（勿回传原文）。
7. `detail.rate_limit_scope`（string \| null）：限流维度（user / ip / route）。
8. `actor_role`（Role \| null）：已在前端类型预留，请响应带上。
9. `resource_type` / `resource_id`：已预留，请稳定返回。
10. `ip`：已预留；演示环境可脱敏为前缀。

### C. 演示 / 安全抽测（可选，需标注 DEMO）

1. `POST /demo/audit/tamper` / `POST /demo/audit/restore`：api.yaml 已有；前端暂不接，待后端 M2 确认 DEMO_MODE 行为。
2. 越权抽测：`reviewer` 调 `/audit/stats` 与 `/audit/logs` 必须 `403 PERMISSION_DENIED` 且记审计。

## 前端承诺

- 生产构建 `VITE_USE_MOCK` 无论 unset 或 `true` 均不触发 mock（见 `scripts/check-prod-no-mock.sh`）。
- 未返回的 provenance / fallback 字段显示「状态信息缺失」或诚实 501/503，不编造文案。
