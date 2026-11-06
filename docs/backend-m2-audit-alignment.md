# 前端 M2 ↔ 后端 `3bbd9b8` 契约对齐说明

相对 `docs/backend-m2-audit-request.md` 的差异以**后端 OpenAPI 0.4.0**为准。

## 已由后端交付并对齐前端

- `SecurityStats`：`window_start` / `window_end` / `generated_at`、`degrade_status`、`llm_verified`、`source_kind` / `source_kind_label`、`totals.csrf_failed` / `auth_locked` / `model_errors` / `outputs_blocked`、timeline 补齐 `logins_failed` / `pii_masked` / `model_fallbacks` / 同上新增计数、`audit_chain_valid`。
- `AuditDetail`（logs.detail）：`source_kind`/`source_kind_label`/`degrade_status`/`llm_verified`/`fallback_reason`/`injection_category`/`pii_fields`/`rate_limit_scope`，以及 `actor_role`/`resource_type`/`resource_id`/`ip`（亦在 AuditLog 顶层重复）。
- DEMO：`POST /demo/audit/tamper|restore`（仅非 prod + DEMO_MODE）。
- 限流：429 `RATE_LIMITED` + `Retry-After`；503 `RATE_LIMIT_UNAVAILABLE`。

## 与请求清单的差异（跟随后端）

| 请求项 | 后端实际 | 前端处理 |
| --- | --- | --- |
| `llm_verified` 可选布尔 | **固定 false**（不把供应方 success/替身当验收） | 一律按未验证标记展示，永不显示「已验证」 |
| `source_kind` 可选 | 必填；看板保守 `synthetic` + 中文未核验标签 | 展示 wire label，不编造 |
| `injection_category` 含 sql/path | 枚举 **prompt / scope / output** | 按后端枚举 i18n |
| `rate_limit_scope` | **user / ip / route**（route 预留） | 按后端枚举 |
| `totals.requests` 含义 | 审计事件数，非 HTTP 请求数 | 文案标明「审计事件」 |
| 端点未就绪 501 | 本 API 已实现；503 用于 Redis/限流存储失败等 | 503 诚实展示；不再把 stats 当骨架占位 |
| 平台 null-tenant 事件 | 不开放给租户角色 | 前端不请求、不伪造 |

## 仍属后端/环境缺口（非前端编造）

1. 真实模型验收仍阻塞（看板 `llm_verified=false`）。
2. 活库 Postgres 往返未在本盒验证。
3. 无外部审计签名锚点；链校验 O(N)。
4. 检测/脱敏为启发式，非完整 DLP。

## 奶龙补充（本提交）

1. **DEMO tamper/restore**
   - 仅隔离夹具（SQLite + fakeredis + `DEMO_MODE` 且 `env != prod`）可用。
   - 后端：`ENV=prod` 即使 `DEMO_MODE=true` 也不注册 `/demo/audit/*`（已代码确认）。
   - 前端：生产构建无 DEMO 入口；`DemoAuditPanel` / `demoAuditApi` 仅 `import.meta.env.DEV` 动态加载；`scripts/check-prod-no-demo.sh` 接入 `build` / prod-no-mock matrix。
2. **基础设施声明**
   - 真实联调截图 sidecar JSON 标注 `database=sqlite_stand_in`、`redis=fakeredis_stand_in`、`postgres_live=false`。
   - **不**宣称数据库级租户隔离或活库 Postgres 迁移已验收（后端跳过 live Postgres）。
