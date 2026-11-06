# M3 本机隔离服务复现说明

所有新下载、构建、数据目录都在 `/workspace/competition/m3-demo-env/`，不在 Git 仓库内。
未调用 apt、Docker daemon、远程数据库或第三方数据库二进制；未改 DNS、代理、镜像源、防火墙或网络限制。
本机原有 `/usr/bin/psql` 仅是客户端，原 5432/6379 无服务端。

## 官方源与校验

- PostgreSQL 18.6：`https://download.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2`
  及同路径 `.sha256`，`sha256sum -c` 通过。
- Redis 官方 stable：`https://download.redis.io/redis-stable.tar.gz` 及 `.SHA256SUM`。
  校验通过后源码 `src/version.h` 和服务 INFO 均为 **8.10.2**。
  stable 会移动，复现应按 evidence JSON 保存的 SHA-256 固定归档，而不是把以后下载的 stable 当成本轮版本。
- 本机缺少 make/m4/bison/flex，均在隔离 tools 前缀构建，未动系统包：
  - GNU Make 4.4.1 官方 ftp.gnu.org 归档，SHA-256 与 Spack/Termux 两处记录一致。
  - GNU M4 1.4.21、Bison 3.8.2 官方 GNU 归档，使用同站 GNU 公钥环验证 detached signatures。
    `Good signature` 不等于 Web-of-Trust 认证；日志保留 GPG 的 unknown-trust 警告，没有伪称完整身份背书。
  - Flex 2.6.4 来自 westes/flex 官方 GitHub release，SHA-256 与 Homebrew formula 一致。
- 全部成功下载/校验输出见 `*-download.log`。无下载网络失败；未重试原 apt HTTP 500 路径。

## 构建

```
# PREFIX=/workspace/competition/m3-demo-env/tools
# GNU Make 首次 configure 因没有 make 的依赖跟踪自举失败，完整保留 make-build.log。
# 随后采用上游提示的无依赖跟踪 bootstrap，不是网络或安全绕过：
./configure --prefix="$PREFIX" --without-guile --disable-dependency-tracking
./build.sh
./make install

# M4、Bison、Flex，各自官方 tarball 目录：
PATH="$PREFIX/bin:$PATH" ./configure --prefix="$PREFIX" --disable-nls --disable-dependency-tracking
PATH="$PREFIX/bin:$PATH" make -j4
PATH="$PREFIX/bin:$PATH" make install

# Redis：仅 core server/cli，无额外 modules、系统安装或持久化：
make -C src -j4 MALLOC=libc USE_SYSTEMD=no BUILD_TLS=no OPTIMIZATION=-O2 redis-server redis-cli

# PostgreSQL：OpenSSL 保留；未安装的可选 ICU/readline/zlib 不构建：
./configure --prefix=/workspace/competition/m3-demo-env/postgres \
  --without-icu --without-readline --without-zlib --with-ssl=openssl
make -j4
make install
```

Redis 仅在 `127.0.0.1:6379`，protected-mode=yes、save=''、appendonly=no，目录 runtime/redis。
Redis live fixture 每个测试另起独立回环临时端口进程，无 FLUSHDB/共享数据清理。
PostgreSQL 仅 `127.0.0.1:5432`，隔离 runtime/pgdata；Unix socket 在权限 0700 的私有目录。
`initdb --auth-local=trust --auth-host=scram-sha-256 --encoding=UTF8 --locale=C`。
Local trust 只用于私有 socket 内的本机测试管理员；应用通过回环 TCP 的 SCRAM 认证。
未使用生产库/用户/文档或对外监听。无 TLS 的回环 Redis/TCP 只证明本机测试环境，不是生产传输加密验收。

隔离库 `st143_m2_test_m3`；迁移角色 `m3_migration` 与运行角色 `m3_runtime` 不同，
二者均 NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE/NOCREATEDB。运行角色不拥有 schema/表。
每个 PG 测试使用随机独立 schema，迁移角色执行 Alembic；运行角色仅获业务表 DML、sequence USAGE
和 alembic_version SELECT。测试结束只删该测试 schema。
固定 `st143_m3_evidence` schema 留作 catalog 证据，不与随机测试 schema 混用。
口令运行时随机生成，0600 本机私有文件保管，未进入仓库、日志、报告或 bundle。

## 测试

必须显式提供 `TEST_POSTGRES_DISPOSABLE=1`、本地隔离 `TEST_POSTGRES_URL`（迁移）与
`TEST_POSTGRES_APP_URL`（不同运行角色），以及绝对路径 `TEST_REDIS_SERVER`。
缺少服务配置会如实 skip；一旦配置，连接失败、角色不安全或 Redis 启动失败均 fail，绝不降级 fake。
环境值不要写进公开命令/报告，测试 runner 直接从本机私有配置注入进程环境。

```
backend/.venv/bin/pytest -q backend --junitxml=reports/progress/backend-m3-demo-env/full.xml
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
bash scripts/security-scan.sh
```

初次 raw PG/RLS/context 测试在原静态启动 hold 未解除时运行，76 项通过（pg-direct-initial.xml）。
随后才把静态 hold 改成真实非 owner 角色、迁移版本、11 表 ENABLE+FORCE RLS、DML 授权和
冻结策略 catalog 的逐次启动检查。策略 manifest 来自本轮通过后的 18.6 catalog；运行时不重新生成它。
策略表达式、适用角色、命令、策略增删或 PG deparser 变化均 fail-closed，需要单独审查，不能自动接受。
真实 API 测试走实际 lifespan，不 monkeypatch 此检查、不 SET ROLE、不借用迁移角色。
配置不兼容的 unscoped PostgreSQL bootstrap 被明确拒绝，运行账号不获跨租户建表/建用户特权。

Redis-only live 测试的数据库是 SQLite 替身。PG-only API 测试的 Redis 是 fakeredis 替身。
`test_m3_postgres_env.py` 的 `test_pg_redis_*` 同时用真实 PG 和真实 Redis；HTTP 为 ASGITransport，
不是生产 HTTPS 部署。OCR 用 quick_ocr；成功答案流用 FakeLLM，绝不是成功真实模型证据。
真实 ProviderChain 的无模型测试必须给出 MODEL_UNAVAILABLE，不生成 assistant 成功消息。
worker startup 测试的数据库检查真实，OCR warmup 单独替换；不据此宣称真实 OCR/模型 worker 全链路验收。

本机 Ollama tags 返回 models=[]（model-preflight.log）；本轮未下载模型、未找/读 API 密钥，
未执行真实 LLM 推理。真实模型 E2E 保留独立 skip，不能由 PG/Redis 结果抵消。
