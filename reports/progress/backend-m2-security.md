# 后端 M2：安全、审计与迁移交付

**本交付不含真实模型验收。** FakeLLM / httpx transport 仅为测试替身；真实模型验证继续单独阻塞，不请求密钥、不混入本次通过项。

## 基线与交付

- 本地分支：`feat/backend-m2-security`。
- 前置 main SHA：`4afc04ea40ab9ec5c5bd573b51b54ae2b01e11eb`；main 保持不变，没有 rebase 或改写已合入历史。
- 功能 tip：`3de89192f20d1f1bff5329e979e9127094a23236`（含 frontend `76830b2` 契约对齐）。
- 后续仅提交本进度/数字证据及安全扫描报告；最终 HEAD 以 bundle 的 `refs/heads/feat/backend-m2-security` 为准。
- 本地 bundle：`/workspace/competition/bundles/feat-backend-m2-security.bundle`，范围 `4afc04ea40ab9ec5c5bd573b51b54ae2b01e11eb..feat/backend-m2-security`，接收仓库必须已有上述前置提交。
- 回归完成：2026-11-05 19:24:54（America/Tijuana，UTC-8）。证据生成：2026-11-05T19:26:08-08:00（America/Tijuana）。
- 只在已存在的本地 worktree 执行；不 push、不建 PR、不使用 CloudAgent、不发群，由奶龙审核推送。

## 五项范围

### 1. 注入与出域过滤

- 输入做 NFKC / HTML 实体 / 零宽归一化，检测伪造角色、关闭鉴权/审计、跨范围请求；递归检查实际字符串，避免 JSON 转义掩盖角色边界。
- OCR / 字段抽取 / 手工字段快照 / 报告 / 召回资料 / 追问路径复用防线；服务层再次校验模型 JSON，测试注入 LLM 也不能绕过。
- 输出剥离凭证、Bearer/JWT/私钥/密码格式，不把它们放入可恢复 PII 映射；拦截提示泄漏、PII、越权与恶意指令残留。旧报告/识别/聊天/审计 JSON 读取也过滤。
- 报告拒绝不安全模型输出时诚实降为 L3，保留确定性规则；追问失败为 `MODEL_UNAVAILABLE`，不造助手成功正文。
- SSE 完整缓冲并检查后才发送 delta，防止跨 token 泄漏；输入拦截保留 `blocked=true`。
- 证据：`backend/tests/test_m2_security.py` **27 passed**；既有 M1 SSE/安全回归全部保留。

### 2. 可配置限流

- 已鉴权写入总桶：租户+用户，默认 300/min；上传 20/min、报告 10/min、追问 JSON/SSE/续传 20/min 独立桶。
- 登录（含失败）按连接 IP 10/min；refresh/logout 共用 IP 30/min。六个 `RL_*_PER_MIN` 配置必须为正整数，0 不代表禁用。
- 超限为 HTTP **429 `RATE_LIMITED`**，Problem JSON、request_id、`Retry-After`；SSE 建流前返回普通 429。写入审计只含维度/额度，不含请求正文。
- Redis 异常 fail closed：**503 `RATE_LIMIT_UNAVAILABLE`**；Redis 事务滑动窗口，拒绝请求不扩张 zset。
- 证据：`backend/tests/test_m2_limits.py` **19 passed**，覆盖十类敏感入口、并发边界、到期、桶隔离、登录失败、SSE 续传、Redis 失败、非法配置。

### 3. 租户/用户隔离

- 同 org 其他 reviewer 与外 org admin 均不能读取/修改/删除他人单证、识别、原件页、报告、追问历史、JSON/SSE 发送或回放，以及案件审计；固定契约为 404。
- reviewer 读取全局租户审计 logs/stats 为 **403 `PERMISSION_DENIED`** 并记审计；外 org 的列表/统计仅能看到其自身租户事件，不能用筛选看到外部记录。
- tenant_id=null 的平台/未知账号事件不再分发给每个组织；verify 的计数/head/坏行 ID 只返回本租户范围，外租户篡改不泄漏其 ID。
- DEMO 以外租户明确 log_id 篡改/恢复均404，不改变目标链。
- 可引用否定测试：`test_cross_scope_document_report_history_replay_and_audit_denied[same_org_other_user]`、`[foreign_org_admin]`、`test_audit_tenant_null_events_secrets_and_verify_no_foreign_disclosure`、`test_cross_org_specific_audit_demo_target_is_404_without_tampering`（均在 `test_m2_audit_isolation.py`）。该模块 **8 passed**。

### 4. 审计看板与前端契约

- `GET /audit/logs`、`/audit/stats`、`/audit/verify` 仅 admin/auditor；`GET /reviews/{review_id}/audit` 按案件权限读取。前端请求原文已原样复制到 `docs/backend-m2-audit-request.md`。
- logs / 案件审计：action/result/actor_id 精确过滤；since 含、until 不含，必须带时区且范围有效；page>=1，page_size=1..100，seq 倒序。时间偏移先统一 UTC，SQLite 与 Postgres 比较语义一致。
- stats：真实落库事件聚合、补零时间桶、top_denied_actors、链完整性；补齐 window_start/window_end/generated_at，csrf_failed/auth_locked/model_errors 和 timeline 的 logins_failed/pii_masked/model_fallbacks。
- auth_locked 计进入锁定状态的次数（不重复计锁定期间重试）；model_errors 计失败的 model.call（非 fallback）；requests 是审计事件数，不是 HTTP 请求总数。
- CSRF 拒绝只有合法签名、未过期 access + 当前可用 DB 用户才归属租户；不信任未验签 claims。
- AuditDetail 显式返回 source_kind/label、degrade_status、llm_verified、fallback_reason、injection_category、pii_fields、rate_limit_scope，并稳定提供 actor_role/resource_type/resource_id/ip。只给脱敏字段类别，不给 PII 原文；旧行投影不会改写哈希。
- **看板和 AuditDetail 的 llm_verified 固定 false**，不把一次供应方 success 或测试替身当作真实验收。source_kind=synthetic 保守覆盖未核验来源，中文标签明确「来源未核验 · 非真实模型验收」；数据仍是真实落库统计，不是 mock 响应。
- injection_category=prompt/scope/output；rate_limit_scope=ip/user（route 仅预留）；fallback_reason=provider_fallback/model_error/unsafe_output 或 null。
- 篡改/恢复步骤及可复现 fixtures：`docs/backend-m2-demo.md`；prod 即使误设 DEMO_MODE=true 也不注册演示路径。
- 证据：`test_m2_frontend_audit_contract.py` **5 passed**，另保留原 `test_audit.py` **5 passed**。

### 5. Alembic

- 新增静态 `0001_m2_initial`，覆盖 **11 张业务表**、索引、外键；SQLite JSON / INTEGER seq 与 Postgres JSONB / BIGSERIAL 分流。
- Compose 一次性 migrate 服务成功后才启动 API；API/worker/CLI 只校验 revision。ENV=test 也执行真实 Alembic，不再依赖 create_all 启动。
- README / Docker / Compose / 依赖锁同步。旧库接管 `adopt-legacy-schema` 必须先备份停写，比较 schema 和主键完全一致才 stamp，禁止盲 stamp/删表重建。
- SQLite 升级、幂等、降级重升、metadata 零差异、旧库数据保留与错误主键拒绝均通过；Postgres **离线 DDL** 通过。
- `test_m2_migrations.py` **4 passed, 1 skipped**：活库 Postgres 未运行，本盒没有 server 二进制，安装索引请求网络500；未绕过。可选一次性本地空库测试有严格 opt-in 和库名前缀保护，详见 README。

## 质量门与数字

| 项目 | 结果 |
|---|---|
| 全量 pytest | **210 passed / 2 skipped / 0 failed / 0 errors**，212项，60.81秒 |
| M2 新增模块合计 | 69项：68 passed / 1 skipped |
| ruff check | 通过，0违规 |
| ruff format --check | 通过，81文件已格式化 |
| OpenAPI | 3.1.0 / API 0.4.0，24 paths / 29 operations（含 DEMO），12个写 operation 均声明429/503 |
| 契约测试 | 5 passed；文档与运行时两份 spec 均校验成功，全路径/方法一致；4个审计 operation 的参数、成功响应和关联 schema 精确对齐；实际审计响应符合发布 schema |
| security-scan | 6工具全部OK，0跳过/0错误；CRITICAL=0 / HIGH=0 / MEDIUM=0 / LOW=0 |
| uv lock --check | 通过 |

命令（仓库根）：

```bash
uv run --directory backend pytest -q --junitxml=/tmp/st143-backend-m2-final.xml
uv run --directory backend ruff check app tests alembic
uv run --directory backend ruff format --check app tests alembic
uv lock --check --directory backend
scripts/security-scan.sh
```

数字证据：`reports/progress/backend-m2-evidence.json`；扫描明细：`reports/security/2026-11-05.md`。扫描对象为上列功能 tip + 报告工作区；最后的报告提交不改应用代码。bundle 生成后须通过 `git bundle verify` 与 `git bundle list-heads`，且工作区干净。

## 已知限制 / 未计入通过项

1. **本交付不含真实模型验收；真实模型仍阻塞。** FakeLLM/httpx 不替代真实模型身份、成功调用及报告证据。
2. 活库 PostgreSQL 往返未验（条件测试 skip）；仅 SQLite 真实迁移和 Postgres 离线 DDL 通过，不能宣称生产 Postgres 已联调。
3. 检测/脱敏是正则启发式，有误报/漏报，不是完整 DLP/语义安全证明；授权原件图片仍保留原始内容。
4. 无数据库 RLS；隔离在服务层执行并由否定测试覆盖。无外部审计签名锚点；链校验 O(N)，不能证明整体重算/删尾未发生。
5. 限流不替代边缘层：请求体/参数校验可先于接口桶；须在可信反向代理补连接数、匿名流量与体积限制。
6. 平台 null-tenant 审计故意不开放给租户角色；需要另行受控的平台运维入口。跨进程全局熔断、每日 token 预算、既有报告二次翻译仍不在本范围。
