# M2 tenant context 补强：候选交付，仍未验收/不可部署

记录时间：2026-11-05 19:51 America/Tijuana（PST）。
分支：`feat/backend-m2-security`。
本轮前置 tip：`b36dbb15c4fec965fd42872e24acae57f458c354`（相对该 tip 增量交付，不包含远程推送）。

## 1. 本轮修复

### 认证前查询与事务顺序

- 登录不通过普通未绑定 ORM session 扫 users。`Database.login_candidate()` 是独立事务、精确匹配
  全局唯一 username 的内部只读凭证能力：先清空 tenant/user/role，再 LOCAL 绑定 exact username。
  该能力不打开 documents/reviews/refresh/audit；SQL 使用绑定参数，结果不对 HTTP 调用者公开。
- 候选账号只在 `credential_only` session 中读取自己的 User 与更新登录计数；拒绝业务表查询、
  任意凭证/角色改写。验密成功才解除 credential-only 并签发会话；未知账号也做 dummy 验密。
- 访问 JWT 先验签、类型、时效、UUID、角色，再在首次 User SQL 前绑定不可切换的 TenantScope；
  账号停用、签名 tid 或 role 与数据库不一致返回 401，不能以旧令牌进入变更后的租户。
- refresh/logout 先校验签名路由证明（tid/sub/role + 随机 nonce），再在该身份范围查 token hash；
  轮换/撤销显式限定 user_id。只存整串哈希，旧不透明 Cookie 需重新登录，不做无上下文全表查找。
- CSRF 拒绝归属查询、模型审计指标查询也使用有界 tenant session。
- SQLite 与 PG 的应用 ORM session 都要求上下文，过滤父子表/别名，校验写入 tenant/owner/parent；
  禁止在应用 session 执行 raw SQL。默认 sessionmaker 未绑定上下文即拒绝；显式 maintenance_sessionmaker/原生连接仍是受信管理能力，不提供给请求。

### 共享物理审计表：按租户独立链

- record 在独立事务重验 actor 的 user/org/role，补齐服务器端角色/用户名，不接受仅 user_id 或伪造归属。
  前驱查询只读本租户；各租户与平台 null 事件各自成链，不需要跨租户读共享全局 head。
- PG 锁按 tenant 派生，LOCAL 上下文先于查询；平台 null 审计仅内部 `audit_platform` 能力可访问，
  不开放业务表，不对组织暴露。没有 SECURITY DEFINER、BYPASSRLS 或 all-tenants GUC。
- verify 必须显式给 admin/auditor TenantScope，并重验实际用户，只校验本租户的行。
  审计 API/详情/统计依旧限本租户，reviewer 看板 403；已有跨租户 history/replay 404 保持。
- OCR 失败、抽取、报告与 SSE 的成功/失败审计都保留 org + actor + role，不再落到无租户平台链。

### worker / inline / SSE

- OCR/review 入队与 inline 均序列化已鉴权 `{org_id,user_id,role}`；执行时先校验形状和当前用户身份，
  再领取该 tenant + owner 的资源。缺少上下文的旧任务、停用账号、错租户/角色任务拒绝，不按资源 ID 猜租户。
- TenantScope 和 CurrentUser 不可变，每个 job/producer/session 独立；不使用全局 tenant ContextVar。
  每次事务 after_begin 均重新设置 LOCAL tenant/user/role，并清空 auth lookup 能力，提交/回滚重置。
- SSE start/生成/入库与 replay 都重新验证身份及 review 可见性；每轮重放核对 Redis metadata 的
  tenant/actor/review。账户撤销或 metadata 不匹配不会入库/重放成功答案，恢复仍不重复调用模型。

## 2. 迁移与兼容边界

- 新 head `0003_m2_auth_audit_context`，前置 `0002_m2_tenant_rls`。
  增量调整 users 的 SELECT-only exact-username 能力；INSERT/UPDATE/DELETE 仍仅 tenant 策略。
  审计加平台 null 专用谓词；SQLite 只推进 revision，**不声称实现数据库 RLS**。
- `docs/api.yaml` 与生成的 OpenAPI 对齐：刷新 Cookie 格式/旧 Cookie 401、组织/角色漂移 401、
  每租户 prev_hash 与 SSE 复核语义已写明，路由和 JSON 字段没有删改。
- **没有重写任何历史 hash**。旧共享链的外租户前驱不会被自动背书；verify 会失败。
  已有共享链数据需要另行审核的完整性核验、归档/切换方案，不能盲目重算或把它当迁移验收。
- 队列是受信内部基础设施，任务上下文不是供外部客户端自由填写的身份凭证。
  GUC 是纵深过滤，不是认证或对 DB 凭证被攻破的防御；SQLite raw SQL 仍无 DB 层隔离。

## 3. 可运行验证

从仓库根目录：

```sh
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
backend/.venv/bin/pytest -q backend --junitxml=reports/progress/tenant-context/full.xml
bash scripts/security-scan.sh
```

**全量 pytest：277 passed，86 skipped，0 failed**。其中 85 项为真实 PostgreSQL 活库测试、1 项为真实模型测试；skip 不计通过。`ruff check` 通过，`ruff format --check` 92 文件通过。新增可运行 tenant-context 测试 33 项通过。最终数字见 `tenant-context/pytest-full.log` / `full.xml`。

新增测试是实际 SQLite 事务 + fakeredis 路径，不 mock 数据库会话：未认证零业务 SQL、
无 scope 拒绝、exact lookup、credential-only、错误 tid/stale role、无签名 refresh 不查库、
多租户/平台审计前驱与 actor 校验、历史链不假绿、单连接池 commit/rollback/exception、并发 job、
worker 丢失/伪造/失效身份、跨 owner/org 不能领取、失败审计归属、ARQ 传参、SSE replay/metadata/撤销，
以及 API/worker 启动保护。已有完整 pipeline、隔离、限流、安全过滤、迁移与 OpenAPI 回归也运行。

证据目录 `reports/progress/tenant-context/`：
- `pytest-full.log`、`full.xml`、`pytest-context.log`、`ruff.log`。
- `postgresql-context-upgrade.sql` 是离线 DDL，不是 PG 执行证据；SQLite SQL 无 RLS。
- `security-scan.log` 与 `reports/security/2026-11-05.md`；CRITICAL/HIGH/MEDIUM/LOW 均为 0、ERRORS=0；semgrep/bandit/gitleaks/trivy/pip-audit/npm audit 均执行，没有 SKIPPED。

新增 5 个真实 PG 能力测试（exact lookup、查询能力不许 UPDATE/DELETE、租户审计链、平台隔离）
继续明确 skip；没有把它们换成 SQLite 或假连接来冒充活库通过。
**真实 PostgreSQL、真实 Redis、真实模型链路均未由本轮验收**；成功 LLM 流均是测试替身，
实际无模型路径仍明确 MODEL_UNAVAILABLE，不伪造成功流。

## 4. 生产启动保护仍在

- `Database.check_runtime_access()` 对 PostgreSQL 在角色检查后仍无条件抛出
  `PostgreSQL RLS deployment blocked: ... requires real non-owner PostgreSQL acceptance ...`。
  没有新增开关、环境变量或 SQLite 通过即可释放该门禁的逻辑。
- `main.lifespan()`、`workers.tasks.startup()` 均在 bootstrap/AI/Redis 工作初始化前调用该检查。
- `test_api_and_worker_startup_keep_postgres_gate_before_ai_redis_and_bootstrap[api/worker]`
  运行真实启动函数（只把数据库/角色前置检查设为测试替身），证明两条入口都拒绝继续初始化。
  这是门禁控制流证据，**不是 PG 启动通过证据**。
- 没有安装/重试 PostgreSQL，没有改网络或安全限制。原 apt 失败日志和前置报告与 b36dbb1 零 diff。
  `reports/progress/postgres-rls/apt-install.log` SHA-256：
  `9ae0a0aa052dbc5ee6d96ddfc01bb82c24b21b59e1cb9169bddf6167d138a030`。

## 5. bundle 与结论

交付目标：`/workspace/competition/bundles/feat-backend-m2-tenant-context.bundle`。
包含本分支相对 `b36dbb15c4fec965fd42872e24acae57f458c354` 的后续提交；接收方须先拥有该前置 tip。
最终 tip / bundle SHA-256 / verify / list-heads 以同目录的
`feat-backend-m2-tenant-context.manifest.txt` 及执行器最终回报为准（避免报告嵌入自身提交 hash）。

本轮仅补独立代码缺口及可运行自动化证据；**M2 仍未验收、不可部署，真实模型仍独立阻塞**。
未 push、未建 PR、未调用 CloudAgent、未发群、未输出或复制密钥。
