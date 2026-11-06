# 后端 M2 PostgreSQL 活库验收：未完成（环境阻塞）

**不可验收为通过：PG 活库迁移、PG 应用隔离、DB RLS 三项均无成功执行证据。**
本次只补齐可复现的活库测试入口、一次性目标保护和明确否定基线；未改生产代码或迁移。
真实模型验证仍单独阻塞。

## 分支与提交

- 起始 worktree 已确认干净，分支 `feat/backend-m2-security`，前置
  `3bbd9b8573d33b871d75c276cf90d4775b35e702`；main 前置仍为 `4afc04e`。
- 功能 tip：`3802fc3559576214af84f244dc4a09a93a8ad42c`；之后仅提交报告/数字证据。
- 新 bundle：`/workspace/competition/bundles/feat-backend-m2-postgres-live.bundle`，
  范围 `3bbd9b8573d33b871d75c276cf90d4775b35e702..feat/backend-m2-security`；
  接收方必须已有前置提交。最终 HEAD 以 bundle 的分支引用为准。
- 全程本地操作；不 push、不 PR、不 CloudAgent、不发群、不展示密钥。

## 环境探测与实际失败

- Python 3.12；SQLAlchemy 2.1.8，asyncpg 0.32.0。
- **PostgreSQL 服务器版本：未知，未启动/未连接。** 已安装的仅为
  `psql (PostgreSQL) 17.11 (Debian 17.11-0+deb13u1)` 客户端，不能当服务器版本。
- `postgres` / `pg_ctl` / `initdb` 不存在；无 Docker / Podman；没有可用本地二进制/包缓存。
- `pg_isready -h 127.0.0.1 -p 5432` 与本地 Unix socket 均为 `no response`。
- 尝试 `sudo -n apt-get update -qq`，Debian trixie / updates / security 索引请求均返回
  HTTP 500，退出 100，后续安装没有执行。没有换镜像、换协议、禁签名、改 DNS 或其他绕过。
- 用无密码的本地专用测试目标显式 opt-in 后，单独执行活库迁移用例：
  **1 setup error / 0 passed / 0 skipped**；连接回环 5432 被拒绝，错误值已脱敏。
  该失败证明显式配置不可连接时不会 skip/假绿，不是迁移运行失败后的数据库结论。

## 已交付的测试入口（尚未在活库运行）

`backend/tests/test_m2_postgres_live.py` 共 10 项：

1. Alembic 升级 `0001_m2_initial`、重复升级、metadata schema 零差异、数据保留、
   downgrade base 后再 upgrade。与 SQLite 复用同一断言，未使用 create_all。
2. 同组织其他 reviewer / 外组织 admin：文档、识别、原件页、报告、追问历史、
   JSON/SSE、Last-Event-ID 回放、案件审计、修改/删除/用于新报告均按权限拒绝。
3. 审计过滤/分页/时间边界、NULL/外租户事件不披露、外租户不能探知本租户断链。
4. admin/auditor 本租户看板与 reviewer 403；隔离 DEMO 的外租户篡改/恢复目标404。
5. 无 RLS 的可复现否定/绕过基线（见下一节）。

安全限制：`TEST_POSTGRES_URL` 优先，亦支持 `DATABASE_URL`；只有缺配置才 skip。
须 `TEST_POSTGRES_DISPOSABLE=1`、本地 loopback/Unix socket、库名以 `st143_m2_test_`
开头；拒绝远程目标、危险连接参数及 SUPERUSER/BYPASSRLS 角色。配置不安全或连接
失败是 error/fail。每例随机独立 schema，通过真实连接 search_path 隔离，结束只清理
该 schema，不清空 public/共享库。12 项离线目标保护测试不算活库证据。

复现（在有真实本地 PG 的环境，backend 目录）：

```bash
# 连接串仅存未入库本地 env；准备有 CREATE SCHEMA 权限的 NOSUPERUSER NOBYPASSRLS 角色。
TEST_POSTGRES_DISPOSABLE=1 uv run --env-file /path/to/local-test.env \
  pytest -q -rs tests/test_m2_postgres_live.py --junitxml=/tmp/st143-pg-live.xml
```

**替身边界**：数据库设计为真实 PG/asyncpg；API 经 ASGITransport，Redis=fakeredis，
OCR=快速 fixture，LLM=FakeLLM。即使将来该模块通过，也只证明 PG 数据库操作/应用授权，
不证明真实 Redis、OCR、LLM、浏览器部署或生产端到端通过。

## RLS 结论与否定检测边界

**DB RLS 未实现。** 静态迁移 `0001_m2_initial` 没有 ENABLE/FORCE ROW LEVEL SECURITY
或 CREATE POLICY；生产代码没有可信租户 DB 上下文机制。本次不在缺少真实 PG 的情况下
追加未经活库验证的 RLS DDL，以免破坏后台 OCR/review、独立 chat producer 和全局审计链。

否定基线 `test_postgres_current_rls_absent_raw_sql_bypasses_application_scope`：

- 先通过 API 确认外租户文档/报告404、审计列表无外部事件；
- 查询本 schema 的 pg_class，要求 11 张业务表 relrowsecurity/relforcerowsecurity 均 false；
- 用NOSUPERUSER NOBYPASSRLS 的应用数据库角色，设置外租户 app.tenant_id/app.user_id GUC，
  故意省去应用 WHERE，预期仍可直接 SQL 读到其他租户文档、报告及审计记录。

**该例尚未运行，不能写成已经观测到 PG 绕过；将来通过只代表 RLS 缺失，不是安全通过。**
现有应用层隔离只有 SQLite/测试替身回归证据，PG 上仍待执行。落地 RLS 时该否定基线
必须改为 enforce 的 SELECT/INSERT/UPDATE/DELETE、无上下文拒绝、commit/rollback/连接池
不串租户验证，并处理 worker 与审计链边界；不能把应用 WHERE 或自定义 GUC 本身称为 RLS。

## 本次质量门

证据时间：2026-11-05T19:32:21-08:00（America/Tijuana）。

| 项目 | 实际结果 |
|---|---|
| 原分支基线全量 | 210 passed / 2 skipped，57.72秒 |
| 本次全量 pytest | **222 passed / 11 skipped / 0 failed / 0 errors**，233项，60.69秒 |
| 其中 PG 活库 | **0 executed / 0 passed / 10 skipped**；不是 PG 通过 |
| 其余 skip | 1项真实 Ollama 测试；真实模型仍阻塞 |
| 新增目标保护 | 12 passed，全部离线 |
| 定向迁移/guard/PG模块 | 16 passed / 10 skipped；通过项为 SQLite/离线 |
| 显式目标连接 preflight | **1 setup error**（预期环境失败），未执行迁移 |
| ruff check / format --check | 通过；84文件已格式化 |
| security-scan | 6工具OK，0跳过/0错误；CRITICAL/HIGH/MEDIUM/LOW 全0 |

复核命令（backend 目录）：

```bash
.venv/bin/pytest -q --junitxml=/tmp/st143-backend-m2-postgres-live-final.xml
.venv/bin/ruff check app tests alembic
.venv/bin/ruff format --check app tests alembic
# 仓库根
scripts/security-scan.sh
```

扫描覆盖功能 tip `3802fc3` 与当前工作区；最后提交只增加本报告/数字及扫描报告。
所有通过数字均不包含 PostgreSQL 活库成功。

原始 JUnit（仅本地）：`/tmp/st143-backend-m2-postgres-live-final.xml`；
失败 preflight：`/tmp/st143-backend-m2-pg-preflight.xml`。
摘要：`reports/progress/backend-m2-postgres-live-evidence.json`；扫描：
`reports/security/2026-11-05.md`。

## 未收口

- 缺可用真实 PG 服务器：迁移与隔离未执行，服务器版本未知，10 项活库全部未验收。
- DB RLS 未实现；可复现否定基线仅已编写、未在 PG 观测。
- 真实模型仍阻塞；不混报 FakeLLM、SQLite、离线 DDL 或测试 skip 为真实成功。
- 下一步需在经批准且已装 PostgreSQL 的环境配置本地一次性数据库后，先跑活库模块、
  保存服务器版本/role/revision 与 JUnit，再决定 RLS 实现及新增迁移。不得据本 bundle 关闭 M2。
