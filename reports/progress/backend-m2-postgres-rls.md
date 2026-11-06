# 后端 M2 PostgreSQL / RLS：候选代码已补，活库与整体集成未验收

**这是部分交付，不是 PostgreSQL / M2 验收通过。** 官方 apt 仍失败，没有 PG 服务器；
RLS 缺口已新增候选迁移，但认证、共享审计链、后台 worker/SSE 的租户接线仍未完成。
为避免误部署，**本分支 PostgreSQL API / ARQ worker 明确拒绝启动**；不得直接部署。
真实模型/检索端到端继续独立阻塞。SQLite、离线 SQL、mock role/session 不算 PG 成功。

## 分支与交付范围

- 分支：`feat/backend-m2-security`；起点干净，前置
  `442f8c1c1c3ab2e75730597e7816098daa0198f1`。
- 实现提交：`68e0e2ab7bf776ea9b014225bca4515a76f5b8b6`。后续提交仅报告/证据。
- bundle：`/workspace/competition/bundles/feat-backend-m2-postgres-rls.bundle`。
  范围 **442f8c1..feat/backend-m2-security**，不是 main 起点；接收方必须已有上述前置。
  最终 tip 以 bundle `list-heads` 和本地最终 HEAD 为准，避免自引用报告 SHA。
- 不 push / PR / CloudAgent / 发群；未展示或持久化真实凭据。

## 安装 / 启动的完整实际过程

实际尝试时间：**2026-11-05 19:33:31 America/Tijuana（UTC-8）**。
启动前确认没有 PG server 监听，只有原已存在的 psql 客户端。

执行的安装 shell（完整控制流，安装仅在 update 成功后执行）：

```bash
sudo -n apt-get update
update_status=$?
printf 'apt_update_exit=%s\n' "$update_status"
if [ "$update_status" -eq 0 ]; then
  sudo -n apt-get install -y postgresql
  printf 'apt_install_exit=%s\n' "$?"
fi
```

结果：`apt_update_exit=100`；**install 分支未执行**。原错误如下，未改写 HTTP/签名错误：

```text
$ sudo -n apt-get update
Err:1 http://deb.debian.org/debian trixie InRelease
  500  Internal Server Error [IP: 198.18.0.1 80]
Err:2 http://deb.debian.org/debian trixie-updates InRelease
  500  Internal Server Error [IP: 198.18.0.1 80]
Err:3 http://deb.debian.org/debian-security trixie-security InRelease
  500  Internal Server Error [IP: 198.18.0.1 80]
Hit:4 https://dl.google.com/linux/chrome-stable/deb stable InRelease
Reading package lists...
E: The repository 'http://deb.debian.org/debian trixie InRelease' is not signed.
E: Failed to fetch http://deb.debian.org/debian/dists/trixie/InRelease  500  Internal Server Error [IP: 198.18.0.1 80]
E: Failed to fetch http://deb.debian.org/debian/dists/trixie-updates/InRelease  500  Internal Server Error [IP: 198.18.0.1 80]
E: The repository 'http://deb.debian.org/debian trixie-updates InRelease' is not signed.
E: Failed to fetch http://deb.debian.org/debian-security/dists/trixie-security/InRelease  500  Internal Server Error [IP: 198.18.0.1 80]
E: The repository 'http://deb.debian.org/debian-security trixie-security InRelease' is not signed.

apt_update_exit=100
```

原始完整 stdout/stderr：`reports/progress/postgres-rls/apt-install.log`。
原日志第一行的字面时区标签不准确（命令使用了宿主默认 TZ）；以上已按其显式偏移换算
为 America/Tijuana。错误原文未改。没有换镜像/协议、禁签名、改 DNS/防火墙或网络策略，
也没有下载替代二进制、从 Docker/其他端点绕过 apt 失败。

后续仅做只读回环 readiness 探测：

```bash
psql --version
# psql (PostgreSQL) 17.11 (Debian 17.11-0+deb13u1) -- 仅客户端
pg_isready -h 127.0.0.1 -p 5432
# 127.0.0.1:5432 - no response; exit 2
command -v postgres pg_ctl initdb
# 无结果，exit 1
```

证据：`reports/progress/postgres-rls/server-preflight.log`。
**服务器未安装成功、未启动、服务端版本未知。没有创建 DB/user，没有修改监听配置。**
预期后续只允许 localhost/127.0.0.1/本地 socket 和隔离库；不能声称已验证 loopback 配置。

## RLS 代码修复（与环境阻塞分开）

新增 Alembic `0002_m2_tenant_rls`，前置 `0001_m2_initial`：

- 11 张业务表全部 ENABLE + FORCE；每表 permissive `tenant_allow` + restrictive
  `tenant_guard`，显式 USING / WITH CHECK，共 22 个策略；无任意 GUC 管理员绕过。
- tenant / users / audit 直接 org 相等；NULL 审计租户不放行。
- documents / reviews 同 org + reviewer 仅 owner，admin/auditor 本 org；owner 必须在本 org。
- refresh_tokens 绑定当前 user 及 org；子表通过父表 EXISTS 继承 RLS，双亲关联同时校验，
  防外租户 reparent，fields.updated_by 也检查 org。
- SQLite revision 显式 no-op：不伪造 SQLite RLS。downgrade 不删表/数据，只移除本策略。
- legacy adoption 改为 stamp 初始 revision 后实际 upgrade，不能只比 metadata 就 stamp head。
- 新 TenantScope 与 tenant_session：事务 after_begin 使用绑定参数 set_config(..., true)，
  commit/rollback 后重设；全新 session 绑定一次身份，避免 ORM identity map 换租户。
  原生连接 helper 必须在 BEGIN 内使用。
- 应用角色检查拒绝 superuser/BYPASSRLS/CREATEROLE/CREATEDB、危险角色成员、表/schema owner
  及其成员。真实测试要求 owner / app 两个独立登录；不是超级用户 SET ROLE 冒充。

上下文示例（合成 ID，仅说明语义）：

```sql
BEGIN;
SET LOCAL app.current_org_id = '00000000-0000-4000-8000-000000000001';
SET LOCAL app.current_user_id = '00000000-0000-4000-8000-000000000002';
SET LOCAL app.current_role = 'reviewer';
SELECT * FROM documents;
COMMIT;
```

详细角色准备/私下注入方式与威胁模型：`docs/backend-m2-postgres-rls.md`。
离线 PG / SQLite upgrade / downgrade SQL 均已保存到
`reports/progress/postgres-rls/{postgres,sqlite}-rls-{upgrade,downgrade}.sql`。
这些是**渲染产物，不是活库执行日志**。

## 活库测试设计与仍未执行的断言

`backend/tests/test_m2_postgres_rls.py`：71 项，全部真实 PG-only，未用 SQLite 替代。

- 迁移策略 catalog、ENABLE/FORCE/22 策略、0002→0001→0002 以及重复 upgrade、保留数据。
  原活库模块仍覆盖 head/base 全量迁移往返与 schema parity。
- 非超级、NOBYPASSRLS、非 owner 的 app 独立直连，对全部 11 表省略 WHERE 做 SELECT；
  外租户 SELECT 不可见、UPDATE/DELETE 0 行，外租户 INSERT 与可见行迁出租户/重挂父记录
  必须是 row-level security SQLSTATE42501，不能靠 unique/FK/授权错误假通过。
- 缺上下文、NULL 租户拒写；同 org owner/admin/auditor 边界；同租户 app 全表 INSERT/UPDATE/DELETE。
- 单连接池验证 pg_backend_pid 不变，A→B→空 scope，多种 commit/rollback/close/异常退出；
  ORM 每次新事务重绑及并发请求。没有仅靠应用 WHERE 的伪 RLS 断言。
- 角色 / owner 检查、明确 PG rollout gate。

目标保护：只有 PG URL 未提供才 skip；指定后连接失败、缺 app URL 或不安全参数/角色都
error/fail。app URL 必须和 owner 同一个 local disposable DB、不同账号；DB 名必须以
`st143_m2_test_` 开头，每例独立 schema，仅清理该 schema。app 只给该 schema 业务 DML、
sequence USAGE 和 alembic_version 的只读权限，不给 schema CREATE / DDL / TRUNCATE。

显式配置无密码的本地合成测试目标，单独 preflight：

```bash
# 仅本地不存在的一次性目标；没有真实密码/密钥
TEST_POSTGRES_DISPOSABLE=1 \
TEST_POSTGRES_URL=postgresql+asyncpg://st143_m2_owner@127.0.0.1:5432/st143_m2_test_rls \
.venv/bin/pytest -q \
  tests/test_m2_postgres_rls.py::test_pg_rls_catalog_all_business_tables_forced_and_restrictive \
  --junitxml=../reports/progress/postgres-rls/preflight.xml
```

实际：**1 setup error / 0 passed / 0 skipped**，`[Errno 111] Connect call failed ('127.0.0.1', 5432)`；
退出1。证明显式不可用目标不会 skip 假绿，不是已运行后的迁移结论。
证据：`reports/progress/postgres-rls/pg-preflight.log`、`preflight.xml`。
旧“当前无 RLS 可绕过”的否定基线已删除，由上述正向 enforcement 断言替代；没有保留
“绕过也算通过”的安全测试。

## 本次实际质量结果

证据时间：**2026-11-05T19:42:14-08:00（America/Tijuana）**；实现 tip `68e0e2ab7bf776ea9b014225bca4515a76f5b8b6`。

| 项目 | 实际结果 | 不可扩展为 |
|---|---|---|
| 全量 pytest | **244 passed / 81 skipped / 0 failed / 0 errors**，325项，61.16秒 | PG 或真实模型通过 |
| PG 活库合计 | **0 executed / 0 passed / 80 skipped**（新 RLS 71 + 原活库 9） | PG 迁移/RLS/池化验收 |
| 其他 skip | 1 项真实模型 | 真实模型可用 |
| 定向回归 | 26 passed / 80 skipped | PG 通过；26 项均 SQLite/离线 |
| 新增离线检查 | 22 passed（含 SQLite seed 数据形状 smoke） | PostgreSQL 行为 |
| 显式 PG preflight | **1 setup error**，连接回环被拒 | 迁移已执行 |
| ruff check / format | 通过，88 文件 | 安全验收 |
| 安全扫描 | 6工具OK，0跳过/0错误，C/H/M/L全部0 | 动态安全/生产端到端通过 |

命令（backend 目录；扫描在仓库根）：

```bash
TZ=America/Tijuana .venv/bin/pytest -q --junitxml=../reports/progress/postgres-rls/full.xml
TZ=America/Tijuana .venv/bin/pytest -q tests/test_m2_rls.py tests/test_m2_migrations.py \
  tests/test_m2_postgres_rls.py tests/test_m2_postgres_live.py \
  --junitxml=../reports/progress/postgres-rls/targeted.xml
.venv/bin/ruff check app tests alembic
.venv/bin/ruff format --check app tests alembic
# 仓库根
scripts/security-scan.sh
```

日志和 JUnit 均入库：`reports/progress/postgres-rls/`。
扫描：`reports/security/2026-11-05.md`（实现提交 68e0e2a + 当前报告工作区）。
摘要 JSON 包含原始证据 SHA256，保留 preflight 错误，不改成 passed。
原活库 API 测试声明 Redis=fakeredis、OCR=fixture、LLM=FakeLLM，且本轮全部 skip；
新 RLS 模块只测 DB，不调用 Redis/OCR/LLM。全量通过项也不宣称真实依赖联调。


## 未收口 / 可用性影响（不是仅环境问题）

1. 官方 apt 失败：PG 服务器没有安装，迁移/RLS/池化活库全部未运行；服务端版本未知。
2. **候选 RLS 不等于完整 PG API 接通。** 登录前 username / refresh-token 的最小权限
   查询入口、NULL 审计事件写入及共享审计链前驱/校验、bootstrap / OCR/review worker /
   独立 SSE producer 的可信租户传播均还未接线。不能直接把原共享 hash chain 按租户过滤
   后宣称有效；本轮未重写历史链或添加 all-tenants bypass。
3. 为防止静默错写/假验收，API / ARQ startup 加 `check_runtime_access()`：检查角色后，
   PostgreSQL 下明确抛出 `PostgreSQL RLS deployment blocked: ...`。**本分支 PG 服务不能启动**，
   无配置开关可绕过；后续补齐调用点和活库全 API 测试后才可移除 gate。SQLite API 不受影响。
4. GUC 可由有任意 SQL 权限的同一 DB principal 修改；此设计防漏 WHERE，不防凭据失陷、
   任意 SQL/GUC 伪造或恶意 DBA。RBAC、FK/unique 侧信道、并发父表/owner 变更和性能还需验收。
5. 真实模型/检索仍阻塞；本轮没有真实 Redis/OCR/LLM/浏览器或生产端到端成功证据。

**M2 必须继续未验收。** 详细数字见 `backend-m2-postgres-rls-evidence.json`；所有实际失败
与 skip 均保留，不能将其改写成 PostgreSQL 或真实模型通过。
