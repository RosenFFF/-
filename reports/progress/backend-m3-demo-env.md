# M3 后端环境证据与 fixture 修复

- 更新：2026-11-06T07:23:12-08:00（America/Tijuana）
- 分支：`feat/backend-m3-demo-env`，基线 `d499513`；main 不合并、不前进。
- **仅交实现与本机隔离环境证据，不宣称生产部署或真实模型已验收。**

## 共享 fixture 修复

复现三个 setup errors：`test_m3_postgres_env.py` 找不到 `workers`。
原因是该 fixture 原来只定义在 `test_m2_tenant_context.py`，其他测试模块不可见。
将已有实现上移到 `backend/tests/conftest.py`，删除原模块定义；全库只有一个 `workers`，
仍为 function scope，沿用合成 Settings 和 monkeypatch 清理，不重复注册、不读取实际模型密钥。
原三个用例独立复跑 **3 passed**，全量运行也全部通过。

## 最终验证

- `backend/.venv/bin/pytest -q backend`（显式注入隔离服务配置）：
  **387 passed / 1 skipped / 0 failed / 0 errors**；115.28 秒。
- `backend/.venv/bin/ruff check backend`：通过。
- `backend/.venv/bin/ruff format --check backend`：94 个文件已格式化，通过。
- `bash scripts/security-scan.sh`：exit 0；**CRITICAL=0 / HIGH=0 / MEDIUM=0 / LOW=0 / ERRORS=0**。
  semgrep、bandit、gitleaks（工作区及历史）、trivy、pip-audit、npm audit 均执行，无 skipped。
- 可交付、无凭据的完整逐用例结果与源码 SHA-256：
  `reports/progress/backend-m3-demo-env/validation-summary.json`。
- 扫描报告：`reports/security/2026-11-06.md`，覆盖当前 HEAD + 工作区及历史；不是声称基线本身含有本轮改动。

## 真实 PG/Redis 活库证据

本轮确实运行 **PostgreSQL 18.6 / Redis 8.10.2** 服务，不是 SQLite/fakeredis 冒充。
服务仅绑定回环，数据库及每测试随机 schema 隔离；未重复 apt 失败安装路径，未修改网络或安全限制。
环境证明见 `backend-m3-demo-env/test-environment.redacted.json`，catalog 快照见同目录 `postgresql-catalog.json`。

| 测试模块 | 通过 | 实际服务与替身边界 |
|---|---:|---|
| test_m2_postgres_rls | 71 | 真实 PG，直接 SQL RLS/跨租户读写、应用角色与连接池上下文 |
| test_m2_postgres_context | 5 | 真实 PG，认证前查询、审计链、任务租户上下文 |
| test_m2_postgres_live | 9 | 真实 PG/Alembic 往返迁移/API，Redis 为 fakeredis；OCR/LLM 不作真实证据 |
| test_m3_postgres_env | 18 | 真实 PG；pg_redis 用例同时用真实 Redis；OCR 为 quick_ocr，成功答案为 FakeLLM |
| test_m3_redis_live | 7 | 真实 Redis；数据库为 SQLite 替身，成功答案为 FakeLLM |

上述 PG 相关模块共 **103 passed，无活库 skip**；Redis 独立模块 **7 passed**。
`test_m2_postgres_target` 的 12 项是目标防护单测，不计入活库数量。

验证覆盖 Alembic schema parity/幂等/往返、跨租户直接 SQL 拒绝、FORCE RLS、
非超级用户/非 BYPASSRLS 的独立非 owner 应用角色、并发连接池复用不串租户、
认证前查询、审计链、worker 启动、SSE 断线与回放、429/Retry-After、真实 Redis 停服后的 503 fail-closed。
迁移和应用角色均为 NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE/NOCREATEDB；运行角色拥有业务表数量为 0。

原无条件 PostgreSQL 启动 hold 只在本轮活库证据成立后改为严格运行时保护：
迁移版本、非 owner 权限、11 张业务表的 ENABLE+FORCE RLS、DML 授权与冻结策略 manifest 全量比较。
八类 catalog/授权/版本漂移以及真实 API/worker 启动中的策略漂移均被拒绝。
SQLite 不能解除 PostgreSQL 保护；运行角色不自动迁移，不做 unscoped bootstrap。

HTTP 使用 ASGITransport；本轮**不是生产 HTTPS/Compose 部署验收**。
manifest 固定于本轮实际 PG catalog，其他版本或策略表达式变化必须复核，不能自动接受。

## 真实模型（仍阻塞/未跑）

- 本轮 Ollama `/api/tags` 模型数量 **0**，未下载模型、未执行真实推理或真实模型调用 E2E。
- 唯一 skip：`tests.test_m1b_realpath.test_real_ollama_upload_to_review`，
  需要 `RUN_OLLAMA_E2E=1` 和可用本机模型。
- 成功 SSE 回答/续传用的是 **FakeLLM**；只能证明协议/存储/隔离，不证明真实回答质量或模型链路。
- 无模型用例走实际 ProviderChain，返回 `MODEL_UNAVAILABLE`；不构造成功答案、不回退成 mock。
- 因此 **llm_verified=false，M1/M2 总体验收不由本轮自动关闭**。

## 凭据与交付范围

- 可交付 `test-environment.redacted.json` 仅保存环境变量名、版本、角色权限布尔值和替身边界，**无连接串/密码/密钥**。
- `.env.example` 的敏感项为空；Compose 的连接串引用环境变量，没有硬编码实际口令。
- 本机原有私有运行配置仍在仓库外，权限 0600，仅由本地 runner 向子进程注入；
  它含实际测试连接凭据，**不复制、不入报告正文、不入 Git、不入 bundle**。
- 原始 `.log/.xml` 可能带连接对象 repr，全部仅本机保留并忽略；已扫描清除连接 URL，
  可交付结果仅用脱敏 JSON、本文及扫描报告。构建细节见同目录 `build-recipe.md`。
- 不推远程、不建 PR、不发群；交 `d499513..feat/backend-m3-demo-env` bundle 供奶龙审查。

### 扫描误报复核

追加提交 `077b21d` 曾将源码路径与 SHA-256 放在同一 JSON 行，generic-api-key 将其中 6 个文件摘要识别为凭据（历史与工作区重复计数为 12）。
已逐个重新计算实际源码 SHA-256，6 个均完全吻合，非密码/密钥。当前 JSON 改为独立 path/sha256 字段；
`.gitleaksignore` 仅列出该历史提交的 6 个精确 fingerprint，不屏蔽目录、规则或未来发现，历史不改写。
