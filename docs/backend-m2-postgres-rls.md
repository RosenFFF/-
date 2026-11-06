# M2 PostgreSQL RLS：数据库层候选实现（禁止视为可部署验收）

> 本轮官方 apt 更新失败，**没有 PostgreSQL 活库通过证据**。SQLite 不支持 RLS，
> SQLite、DDL 渲染和 mock role/session 测试只能证明离线逻辑。
> `0002_m2_tenant_rls` 是数据库层候选修复；**完整 PostgreSQL API/worker 尚未接通**。
> API 和 worker 在 PostgreSQL 配置下明确拒绝启动，不得直接部署这组提交。

## 迁移与覆盖

新 head：`0002_m2_tenant_rls`，前置 `0001_m2_initial`。

- 11 张业务表全部 `ENABLE` + `FORCE ROW LEVEL SECURITY`。
- 每表一个 permissive `tenant_allow` 和一个 restrictive `tenant_guard`，均有
  `USING` / `WITH CHECK`。后续新增 permissive 策略不能 OR 掉 restrictive 租户约束。
- `tenants.id`、`users.tenant_id`、`audit_logs.tenant_id` 按 org 相等过滤；NULL 审计租户
  **不向任何普通租户放行**。
- `documents` / `reviews` 要求 org 一致，reviewer 只看自己；admin/auditor 可看本 org。
  owner 必须属于该 org，不能借用外组织 user id。
- `refresh_tokens` 必须属于当前 user，且 user 属于当前 org。
- `ocr_pages` / `document_fields` 经 documents 继承可见性；fields.updated_by 必须在本 org。
- `review_documents` 必须同时能看到对应 review 和 document，不能跨组织重挂父记录。
- `chat_messages` 同时检查 org 与 review；`demo_tamper_backups` 经 audit_logs 继承 org。
- SQLite upgrade/downgrade 此 revision 显式 no-op，只推进 revision，**没有等价 RLS**。
- downgrade 仅移除本 revision 的策略及 ENABLE/FORCE，保留数据和初始 schema。
  **降级会移除安全边界，只允许隔离验收库；不得作为生产恢复操作。**
- legacy schema adoption 仅 stamp `0001_m2_initial`，然后真实 upgrade head；不再以 metadata
  相同为由直接 stamp head，避免“有版本号、没有策略”。

## 可信租户上下文：必须事务级

以下仅示意合成 UUID，不能从请求头/查询参数盲取：

```sql
BEGIN;
SET LOCAL app.current_org_id = '00000000-0000-4000-8000-000000000001';
SET LOCAL app.current_user_id = '00000000-0000-4000-8000-000000000002';
SET LOCAL app.current_role = 'reviewer';
SELECT * FROM documents; -- 故意省略 WHERE，RLS 仍应过滤
COMMIT;
```

运行时 helper `app.db.tenant.TenantScope` 校验 UUID 与角色；`Database.tenant_session(scope)`
每个事务的 `after_begin` 用**绑定参数**执行 `set_config(..., true)`，包括 commit/rollback
后的新事务。未绑定的 ORM session 会在每个事务显式写入空 scope，fail closed。
每个身份用全新 session，拒绝事务中绑定或在同一 session 改身份（避免 identity map 泄漏）。
原生连接用 `async with engine.begin()` + `await set_local_scope(conn, scope)`；helper 拒绝
在 BEGIN 外调用。连接池覆盖同一物理连接的 A→B→空→A→空、commit、rollback、异常、close，
以及 ORM 重开事务和并发请求。**这些活库断言本轮未执行。**

禁止 `SET SESSION`、`set_config(..., false)`、连接启动时持久设置租户，禁止继承请求
ContextVar 给独立 producer 当作授权。每次新事务都须绑定完整且已验证的身份。
普通 `SELECT` / 外租户 `UPDATE` / `DELETE` 被策略隐藏时通常是 **0 行**，不是 SQL 异常；
伪造 `INSERT` 或将可见行转移到外租户才断言 SQLSTATE **42501** 且含 row-level security，
不把 FK、唯一约束或表授权错误冒充 RLS 通过。

## 两个独立连接角色（仅测试库示例，未在本机执行）

由已授权的本地 cluster 管理员正常配置，保持官方 SCRAM/peer 认证；不使用 trust、不暴露
公网、不禁签名、不改镜像。凭据私下设置/注入，不能写进 git、报告或群聊：

```sql
CREATE ROLE st143_m2_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE st143_m2_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE DATABASE st143_m2_test_rls OWNER st143_m2_owner;
REVOKE ALL ON DATABASE st143_m2_test_rls FROM PUBLIC;
GRANT CONNECT ON DATABASE st143_m2_test_rls TO st143_m2_app;
-- 切到该隔离库后：REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- 不给 app owner 角色成员资格、CREATE、TRUNCATE、REFERENCES 或 DDL 权限。
```

服务器配置只允许 `listen_addresses='127.0.0.1'` / localhost（或仅 Unix socket），不修改
防火墙和网络限制。**本轮没有安装服务器，所以上述配置没有被实际应用。**

`TEST_POSTGRES_URL` = owner URL，`TEST_POSTGRES_APP_URL` = 独立 app URL，
`TEST_POSTGRES_DISPOSABLE=1`。两 URL 必须同一个 loopback/socket、port、DB，DB 名
以 `st143_m2_test_` 开头，登录角色必须不同。fixture 每例创建随机 schema，owner 跑迁移；
仅向该 schema 授予 app USAGE、业务表 DML、sequence USAGE，结束只删该随机 schema。
没有用超级用户 `SET ROLE` 假扮 app，断言来自 app URL 的真实独立连接。
测试 fixture 中 owner 也不是 superuser/BYPASSRLS；其 seed DML 仍受 FORCE 与事务上下文限制。

`check_application_role()` 拒绝 superuser、BYPASSRLS、CREATEROLE、CREATEDB、这些角色的
成员、RLS table owner（含成员）与 schema owner。生产 app 必须不拥有表且无 DDL 权限；
仅 NOBYPASSRLS 还不够，因为 table owner 能主动 DISABLE RLS。

运行（backend 目录，环境变量须事先私下设置；命令不含连接串）：

```bash
.venv/bin/pytest -q -rs tests/test_m2_postgres_rls.py \
  --junitxml=../reports/progress/postgres-rls/rls-live.xml
.venv/bin/pytest -q tests/test_m2_postgres_live.py::test_postgres_alembic_schema_parity_idempotence_and_roundtrip
```

只有未配置 PG 才 skip。配置后连接失败、少 app URL、不安全 role/target 都 error/fail。
原 `test_m2_postgres_live.py` 的完整 API 项将被 rollout gate 拒绝，不能拿新 DB 单测代替
API 联调。旧“无 RLS 可绕过”的否定基线已删除，不能作为这轮安全通过数字。

## 尚未打通的代码边界（不归因于环境）

本轮**没有**把所有生产会话改成可运行的租户路径：

1. 登录前只知道 username、refresh 前只知道 token hash；users / refresh_tokens 已受 RLS。
   需要单独设计最小权限认证入口，不能通过任意 `app.is_admin=true` / 全租户 GUC 放行。
2. 审计现在是共享物理 hash chain，record 的前驱读取与 verify 的跨租户前驱都不能在
   租户过滤后假装正确；NULL 租户安全事件也需要有明确身份的内部审计写入路径。
   本轮没有重写历史链、没有篡改历史 hash，也没有设置 all-tenants bypass。
3. OCR/review worker、独立 SSE producer 和 bootstrap 要显式传递经验证的租户/actor 身份。
   本轮只交付 scoped session 原语与池化测试，**没有完成这些调用点的接线**。

因此 `Database.check_runtime_access()` 在 PG 下先检查角色，再明确抛出
`PostgreSQL RLS deployment blocked: ...`，API 和 ARQ worker 在 bootstrap / 模型初始化前停止。
这个 gate 没有可开绕过的配置；后续须补齐上述路径和活库 API 测试后才能移除。
这是有意的可用性阻断/集成缺口，不是“PG 主链路可用”。SQLite API 回归不受 gate 影响。

## 威胁模型 / 未声明的保证

自定义 GUC 可被拥有任意 SQL 能力的同一 DB principal 修改。该模式防遗漏 WHERE，
**不防应用凭据失陷、任意 SQL 注入后伪造 GUC 或恶意 DBA**。role 也只能由可信服务器取值，
不能由客户端自报；API RBAC 仍须限制 auditor 写操作。RLS 不覆盖 TRUNCATE/REFERENCES，
唯一/FK 检查也可能产生存在性侧信道，故 app 不授相关特权并须保留 API 的统一错误处理。
父表/owner 变更并发、权限撤销竞态与生产性能未验收；禁止据此宣称全量租户安全通过。
真实 LLM/检索链路仍独立阻塞，RLS 单测不证明任何模型或真实 Redis 成功。

参考：PostgreSQL 17 官方
[Row Security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)、
[SET LOCAL](https://www.postgresql.org/docs/17/sql-set.html)。
