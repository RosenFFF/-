# 前端 M2 审计看板（对接 backend `3bbd9b8`）

## 交付

- 分支：`feat/frontend-m2-audit`（基线 main `4afc04e`，骨架 tip `76830b2` + 本提交）
- Bundle：`/workspace/competition/bundles/feat-frontend-m2-audit.bundle`（`4afc04e..feat/frontend-m2-audit`）
- 后端对照：`feat/backend-m2-security` HEAD `3bbd9b8`（功能 tip `3de8919`）
- 契约：`docs/api.yaml` 同步 0.4.0；差异见 `docs/backend-m2-audit-alignment.md`

## 范围

1. 类型/客户端对齐 OpenAPI `SecurityStats` / `AuditLog` / `AuditDetail`；429 读 `Retry-After` 倒计时、不自动重试；503 `RATE_LIMIT_UNAVAILABLE` 诚实展示。
2. 审计看板接真实 API：admin/auditor 可读；reviewer 403；injection/PII/provenance/`llm_verified=false` 标记。
3. DEMO tamper/restore：仅 DEV 动态入口 + 隔离夹具；生产 `check-prod-no-demo.sh`；后端 prod 不注册路由（已确认）。
4. 真实联调：Alembic migrate → SQLite+fakeredis 夹具 HTTPS（Vite 代理）；截图 sidecar 标明 stand-in。

## 检查

### 替身 / 本地（mock & 单元）

| 项 | 结果 |
| --- | --- |
| oxlint | 通过（仅 set-state-in-effect warning） |
| vitest | 94 passed |
| prod-no-mock matrix（unset / forced true） | OK |
| prod-no-demo（同 matrix + build） | OK |
| mock e2e 390/1440 axe/overflow/keyboard | 2 passed |
| npm audit --omit=dev | 0 vulnerabilities |
| security-scan | CRITICAL=0 HIGH=0 |

### 真实后端夹具（非活库 Postgres/Redis；真实模型仍阻塞）

| 项 | 结果 |
| --- | --- |
| Alembic upgrade head | `0001_m2_initial` on SQLite stand-in |
| real-audit e2e 390/1440 | admin / auditor / reviewer-403 / rate-limited + cross-tenant API 403/404 |
| 基础设施 | `database=sqlite_stand_in`, `redis=fakeredis_stand_in`, `postgres_live=false` |
| 真实模型 | blocked（看板 `llm_verified=false`） |

## 截图

`/workspace/competition/screenshots/m2/real-audit-{admin,auditor,reviewer-403,rate-limited}-{390,1440}.png`（各附 `.json` 基础设施声明）

## 后端缺口（不宣称已验收）

- 真实模型验收仍阻塞
- 活库 Postgres 往返未跑（后端 skip）
- 无 DB RLS / 外部审计锚点；检测为启发式
