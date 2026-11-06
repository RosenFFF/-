# backend-m3-demo-env

分支：`feat/backend-m3-demo-env`（前置 main `d499513`）

## 本轮修复
- 将 `workers` fixture 上移到 `backend/tests/conftest.py`，供 `test_m3_postgres_env.py` 与 `test_m2_tenant_context.py` 共享复用。
- `reports/progress/backend-m3-demo-env/*.log` / `*.xml` 已 gitignore（可能含连接串形态）。
- 私有 `m3-demo-env/runtime/test-environment.json`（mode 600）**不入仓**；仓库仅保留 `test-environment.redacted.json`。

## 验证（本机）
- pytest：`387 passed / 1 skipped`（跳过项为真实模型相关，非 PG/Redis）。
- ruff check/format：通过。
- security-scan：CRITICAL=0 HIGH=0 MEDIUM=0 LOW=0 ERRORS=0（`reports/security/2026-11-06.md`）。

## 活库证据（与模型分开）
- 本机隔离构建 PostgreSQL 18.6 + Redis 8.10.2（官方源码，非 apt；见 `backend-m3-demo-env/build-recipe.md`），仅绑定 `127.0.0.1`。
- 注入私有 env 后跑通 PG/RLS + 真实 Redis 相关用例（含 worker 非 owner 启动门禁、策略漂移拒绝、PG+Redis SSE/限流路径）。
- **真实模型调用 E2E：未跑 / 仍阻塞**，不得与活库通过混报。

## 已知限制
- M3 环境证据仅本机隔离实例；不等于生产验收。
- 启动 fail-closed / 策略 catalog 门禁保留。
- 路演前需按 build-recipe 复现服务；口令仅私有文件持有。
