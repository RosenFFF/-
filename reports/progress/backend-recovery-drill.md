# ST-143 c75f877 restart / recovery drill

分支 `feat/backend-recovery-drill`，基线 `c75f877e09decd1b598c26f25e6b70e8742660d7`。匿名只读 fetch，无 push。本文时钟使用 PST（America/Tijuana）。

## A. 8002 更新及必须说明的运行限制

核验旧 PID **1047443** 的 cmdline（uvicorn / serve_live_pg / 8002）和 cwd（c8c9a00 backend）后，仅向该 PID 发 SIGTERM，pidfd 确认退出。新实际 uvicorn PID **1341808**，完整源码 hash 固定 c75f877，仅绑定 **127.0.0.1:8002**。

- 源码 `/workspace/competition/live-deepseek-c75f877-src`；harness `/workspace/competition/live-browser-pg-redis-deepseek-c75f877/`。旧目录未覆盖。
- 新随机 `st143_dsc75_browser_*` schema；真实 PG5432 + Redis6379/DB12；m3_runtime 非 owner、无 superuser/bypass/DDL 特权；原 Alembic、冻结 RLS manifest/startup gates 全部保留；环境证明 mode600。
- 初始和演练后最终 smoke 均 **readyz200 / login200 / models200 / L0 / DeepSeek healthy**；最终仍为同一 PID，未为任何故障恢复重启8002。只有健康探针，无真实 upload/review/chat。
- Secure-cookie/Origin 配置未放松；smoke 的 loopback HTTP 是内部代理 hop，不是浏览器 HTTPS E2E。云端 TLS 校验未关闭。

**重要限制（不能把此次8002称为不受限的完整推理服务）：为确保全程≤3次模型调用，本次启动临时装入了 health-only BudgetTransport。它仍留在8002进程，拒绝正常推理 POST，且第3次 alias probe 后继续探针会触及预算上限。最后实测 L0 不代表无限持续 L0 或完整上传→LLM能力。此限制是本次操作装入的保护，不是 c75f877 产品代码行为。未擅自二次重启来解除它。下一次获得批准的常规部署/重启必须去掉该临时 transport 赋值；这是一项未解除的运行限制，不能按完整推理服务已恢复来验收。**

## B. 共享服务安全检查与隔离拓扑

事先只读检查 pg_stat_activity（usename/datname/application_name；原 query 仅在内存提取 schema marker，不保存原文）和 Redis CLIENT LIST（db/name）。发现 PG **2** 个客户端、Redis **2** 个客户端，存在无法归属的 unnamed 客户端，不能证明全是本 harness。因此 **共享PG5432/Redis6379重启次数=0**；8002从未被用于注入数据库/Redis故障。

使用同一 demo-env 构建的 PostgreSQL/Redis 可执行文件，新建私有集群 **5433**、Redis **6380**、c75f877 drill API **8003**，全部127.0.0.1。PG本地socket目录700、TCP SCRAM认证；临时 owner/runtime 密码只在内存和 child env，未写明文配置；复用现有 harness 的迁移/授权与原应用 FORCE RLS门禁。Redis protected-mode=yes，不 DROP/FLUSH 共享数据。

DeepSeek 通过只属于8003 transport的 **127.0.0.1:8899 CONNECT relay**：只允许 api.deepseek.com:443，转发原始加密TLS字节，不代理解密、不签发证书、不记录头/body，HTTP客户端保持默认证书验证。停/启relay即可在不改API进程、不改key文件的情况下制造/移除云端不可达。

为节约付费 alias probe，8003使用实际官方 /models 列出的 canonical ID **deepseek-flash**；8002保持原 deepseek-chat alias。canonical ID 的 /models 健康判断是真实请求，但不构成一次真实内容推理验证。Ollama qwen2.5:7b健康来自真实 /api/tags；**L2在此仅是健康/路由级证据，不声称此前失败的本地完整推理流程已被修复。**

## 外部观察（原始错误体均脱敏保留）

时间从故障移除指令前的 monotonic 计时开始。第一列恢复时间是首次 readyz200+L0；第二列包含随后的双账号登录、访问与直接RLS检查完成时间，并非生产SLA。

| 故障 | 故障中 readyz / models | 登录 / 已认证读取 | 同一API PID? | 首次ready / 全套核验(s) | 恢复后 |
|---|---|---|---|---|---|
| 独立Redis停止 | readyz503（Redis unreachable，模型level仍L0）；models200/L0 | 两登录503 RATE_LIMIT_UNAVAILABLE；各自doc200、跨租户404 | 1344197 不变 | 0.106 / 0.316 | ready/login/models200，L0，RLS通过 |
| 独立PG停止 | readyz503（database unreachable，健康level L0）；认证models500 | 登录500或HTTP ReadError；读取500/ReadError，无文档返回 | 1345511 不变 | 0.117 / 0.323 | ready/login/models200，L0，双租户隔离及重连RLS通过 |
| DeepSeek relay停止 | readyz200/degraded L2；models200/L2，DeepSeek unhealthy、Ollama healthy | 两登录200；各自doc200、跨租户404 | 1345511 不变 | 15.578 / 15.740 | ready/models200、L0，双租户隔离/RLS通过 |

模型level只表示AI provider状态，不表示数据库/Redis可用性；PG中断时无法从认证 /system/models取得level，表内L0来自未认证readyz的独立模型检查，不能写成“models200”。

### 租户隔离

使用两个不同 Tenant 的两个真实合成账号。故障前/后以及Redis、relay故障期间：各自文档200，跨Tenant文档404；直接以 **m3_runtime** 执行没有 WHERE 的 SELECT，未设置scope时0行、A/B scope各1行且只含本人。检查documents/users/tenants/reviews的 FORCE RLS 和非owner；startup另外检查完整冻结manifest及全部表。

PG完全离线期间直接RLS查询不可能完成，记为 unavailable/unknown，而非“RLS通过”；API500/transport error均未返回文档。PG恢复后的真实HTTP请求和直接SQL隔离检查通过。额外真实PG测试使应用Session的物理连接invalidate，再rollback/重新begin，确认三项GUC自动重新应用，两个Tenant轮换仍只读本人，最后无scope仍0行。

### cheap路径与覆盖限制

没有运行真实字段提取、有效上传、review推理或chat。空document_ids review探针：Redis中断503、PG中断500、正常及云端中断时422 VALIDATION_FAILED。操作脚本的“invalid upload”错误使用了 `/documents/upload`，实际得到405（PG故障也有transport error），**这不构成正确上传端点/上传验证/恢复能力证据**，原数据保留，不补造结果。

### 探针与断路时间

云端故障前先停relay并等待16s，使原15s健康缓存过期。故障探针失败于list_models，DeepSeek变unhealthy；恢复relay后负结果仍缓存约15s，逐秒轮询于15.578s观察到L0，无API重启。配置probe timeout为4s，连接拒绝没有用满timeout。所有实测 circuit_open=false；此次只健康检查，未触发chat请求断路器，不能把健康缓存恢复说成断路器重置。默认失败阈值3、reset60s仅作为配置记录，未进行付费的真实断路器压测。

## 观察器问题与代码修复

首次观察器在Redis完整测量后，PG故障期间遇到HTTP ReadError，因没有捕获客户端transport异常而终止；只清理了自建实例。该次失败记录在 timings-attempt1.json，不声称其PG已自动恢复。随后修复观察器：将无HTTP响应的transport_error单独记录（不伪造HTTP599等状态），在**新建的另一独立8003实例**完成剩余PG/relay测量。因此不同fault的PID可能不同，但每个成功fault期间/恢复后的PID均不变。8002从未因观察器失败重启。

c75f877实际PG连接异常导致通用500，并伴随复用HTTP连接的ReadError。新增小范围产品修复：OperationalError、失效连接DBAPIError、ConnectionRefusedError -> **503 DEPENDENCY_UNAVAILABLE**，只记录异常类，不记录SQL/DSN/body；未分类DBAPI错误仍为通用500，避免把编程错误伪装为瞬时故障。ASGI测试验证三种瞬时错误、非瞬时500、无私有详情、故障移除后同app恢复。**该修复只在本分支离线验证，8002/实测8003均固定c75f877，不能声称现场已经变成503或消除了真实HTTP ReadError。**

## 调用与消费

整个受计量live期间：真实 **alias inference POST=2**（8002初始/最终健康探针，max_tokens=1），正常内容模型调用=0，chat=0。health/discovery GET尝试 **14**（含Ollama标签及失败请求，不全是云请求）；账户balance GET=2。消费仅记录差额 **CNY0.00**，不记录实际余额；显示精度、结算滞后、共享账户并发均可能影响差额，不能宣称最终免费。硬上限为3；当前持久guard限制如A节所述，不应遗漏。

## 验证与命令

- Targeted recovery tests: 8 passed，4.43s
- Full regression, private live PG/Redis child env, paid opt-ins skipped: 487 passed / 7 skipped，118.81s
- Ruff / Bandit app+eval / Gitleaks工作树+提交范围 / 实际key进程内字节比较：最终回执见证据。

```sh
# cwd backend；不打印/复制私有配置，只注入child env；全部RUN_*及云key移除
python3 /workspace/competition/backend-recovery-drill-evidence/run_regression_private.py tests/test_recovery_drill.py
python3 /workspace/competition/backend-recovery-drill-evidence/run_regression_private.py
# cwd repo root
ruff check backend
bandit -r backend/app backend/eval -q -f json -o /workspace/competition/backend-recovery-drill-evidence/bandit.json
gitleaks dir . --redact --no-banner --report-format json --report-path /workspace/competition/backend-recovery-drill-evidence/gitleaks-worktree.json
python3 /workspace/competition/backend-recovery-drill-evidence/verify_key_absent.py
gitleaks git . --redact --no-banner --log-opts='c75f877..HEAD' --report-format json --report-path /workspace/competition/backend-recovery-drill-evidence/gitleaks-range.json
```

操作脚本为已执行存档，不应盲目复跑；包括共享只读检查、严格预算、固定端口独立实例、安全cleanup和CONNECT relay。未保存实际余额、key、DSN或临时PG密码；未把私有PG数据目录或加密storage打入Git。环境证明现场权限600，Git不保留600权限位。

主证据 `reports/evidence/backend-recovery-drill/recovery-summary.json`；完整attempt与错误体、原样脚本、脱敏日志和SHA256SUMS位于同目录。外部 `/workspace/competition/backend-recovery-drill-evidence/`；8002现场harness目录见A节。bundle范围c75f877..tip；最终commit、scan及bundlehash回执外置，避免自引用。
