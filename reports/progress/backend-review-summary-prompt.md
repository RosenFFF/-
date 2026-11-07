# ST-143：8002 更新、保留有效摘要、五例提示词验证

- 分支 `feat/backend-review-summary-prompt`；基线 `c8c9a00009612a7fec60b44193795d9a9ac8180c`；仅本地提交和 bundle，不推送。
- 正式定位仍为「云模型为主、规则引擎降级」。以下付费结果均为真实 DeepSeek；不声称已具有本地 L2 全流程能力。
- 本记录不含文档文本、字段值、凭据或账户余额。时间均按 PST（America/Tijuana）。

## A. 已先更新 8002，保持固定在 c8c9a00

2026-11-07 02:09 PST，检查 cmdline/cwd 后仅对旧 8002 PID **539339**（71311f4 uvicorn）和过时 8001 PID **496807**（aaee76a uvicorn）发出 SIGTERM，并用 pidfd 验证退出。Ollama PID123684、PG、Redis 未停止。新实际 uvicorn PID **1047443**，仅监听 `127.0.0.1:8002`。

- detached 源码：`/workspace/competition/live-deepseek-c8c9a00-src`；启动脚本检查完整基线 hash。
- 新 harness：`/workspace/competition/live-browser-pg-redis-deepseek-c8c9a00/`；旧 harness 源码/目录未覆盖。
- 隔离的新 `st143_dsc8_browser_*` schema；真实 m3_runtime + FORCE RLS；运行 Alembic/原启动门禁；Redis DB12。不 DROP/FLUSHDB，不复用旧 schema。
- 私有配置仅进程内读取/子进程环境注入；实际 `environment-proof.json` 权限 600，JWT/KEK 只在内存；日志抑制 DSN/URL 并脱敏凭据。
- `/api/v1/readyz` **200**，带指定 Origin 登录 **200**，`/api/v1/system/models` **200**；**L0、DeepSeek healthy**。smoke **1704 ms**，readiness/models 共用 15 秒健康缓存。
- A 仅健康探针，review/upload/chat 均 0；没有为 A 添加额外推理验证。未单独计量探针内部的计费调用数，不与 C 的 10 次混算。
- Secure-cookie 配置未放宽。登录 smoke 是内部 loopback/proxy-hop HTTP 测试，cookie 只在内存，不是浏览器 HTTPS E2E；无 TLS 校验关闭。
- **运行中的 8002 仍是 c8c9a00，不是本分支。B/C 后未重启它。**

启动/核验记录：`python3 /workspace/competition/live-browser-pg-redis-deepseek-c8c9a00/launch_redacted.py`；start.sh 的 full-hash gate、进程终止核验、smoke 状态及原始校验和见证据。不要重复执行 smoke 产生多余健康探针。

## B. 只重建涉及已过滤结论的摘要

`model_findings.py` 仅在 unsupported finding 被移除时收集其 citation IDs，不改变 `model_output_filter` 计数。仅当原摘要包含被删除的规则 ID，或该规则的小型关键词表时，才用**保留 findings** 重建：风险等级、严重性/分类计数、排序后的保留规则 IDs，末行 `已过滤 N 条无依据结论`。N 是被删 finding 对象数，不是去重后的 sample-rule 对数。

关键词：ORIGIN 原产国/原产地/origin；AMOUNT 金额/总额/amount；HS hs/海关编码/税则；REQUIRED 缺失/缺少/missing/required；RESTRICTED 禁限/禁运/restricted/embargo。英文采用字母数字边界，避免 months/original 误匹配。仅 dedupe 不触发重建；不相关原文原样保留。不恢复 PII，不把已删结论搬回摘要。

**历史 20 条离线审计：摘要正文缺失 20/20，因此 kept/rebuilt 均无法判定，unknown=20。** known_kept=0、known_rebuilt=0 只是“已知计数”，不是实际全部重建或全部保留。历史账本可复验过滤条件/计数，不能验证原文关键词是否命中；没有为此调用模型。新五例在实际摘要调用处只保存决策布尔值：**保留 4，重建 1（sample12）**，不保存摘要正文，故同样不能离线重新执行文本匹配；匹配策略由离线单元测试覆盖。

## C. 一次且仅一次：5 个 review，无 chat

预先固定样本 **1、9、12、15、18**，分别覆盖 clean、missing、HS、amount、restricted。使用与历史账本相同的合成样本；只执行五例一次，不重跑。私有 wrapper 使用独占启动标记，capture 目录非空拒绝复跑，模型 HTTP 硬预算 10。

实际 review prompt 明确所有触发条件：doc-type required keys；已提供 HS 才检查 6/8/10 位格式；三个金额字段齐全才校验数值/有限非负及差额 >0.01；仅命中两个显式 restricted markers；**同一 review 的多个文档有 >1 个不同非空 origin_country 才可 SYN-ORIGIN，单文档绝不引用**；范围提示不是异常，泛化建议不得冒用未触发的合成规则。

每个样本在开始、提取后、确定性条件得出后、模型 findings citation 校验后、报告持久化后分别原子写盘/fsync；先写 ledger 再计算指标。只记录 ID、来源、严重性、分类、field keys、mismatch keys、条件布尔值和计时，不存文档/字段值。新五例全部完成，提取和 review **5/5 L0、DeepSeek、llm_verified=true**，没有降级冒充模型。

调用计量：**10 次模型 HTTP**（提取5 + review5，均 HTTP200），**chat=0**，余额 GET=2（run 前/后）；仅保存差额 **CNY 0.00**。余额差额以接口显示精度/结算时点为限，不能宣称免费或最终扣费为零；不保存前后余额。A 的健康探针不在该差额区间内。

### 指标定义与同五例对比

按唯一 `(sample_id, rule_id)` 计数；排除范围说明 SYN-REVIEW；hit=标签内命中、extra=标签外引用、miss=预期但未命中。extra 不自动等于事实 FP；公开资料建议未做事实裁定。真实合成规则 FP 需同时是标签外模型引用，且该样本实际确定性前提为 false。两个 run 的五例实际条件布尔值完全一致。

| 同五例 | hit | extra | miss |
|---|---:|---:|---:|
| 历史 prompt，过滤前 | 4 | 22 | 0 |
| 历史 prompt，原有输出过滤后（离线） | 4 | 8 | 0 |
| 新 prompt，过滤前 | 4 | 5 | 0 |
| 新 prompt，输出过滤后（实际报告=离线 replay） | **4** | **4** | **0** |

| 真正模型 FP 的规则 | 历史过滤前 | 新过滤前 | 新过滤后 | 新 FP sample ids |
|---|---:|---:|---:|---|
| SYN-REQUIRED | 4 | 0 | 0 | — |
| SYN-HS | 1 | 0 | 0 | — |
| SYN-AMOUNT | 4 | 0 | 0 | — |
| SYN-RESTRICTED | 0 | 0 | 0 | — |
| SYN-ORIGIN | 5 | 1 | 0 | 12 |
| 合计 | **14** | **1** | **0** | 12 |

新 prompt 仍产生一次不满足前提的 ORIGIN 结论，不能声称提示词消除了幻觉；输出层将其移除，确定性 findings 不删除，**miss 保持0**。

| 标签外桶/规则 | 历史过滤前 | 新过滤前 | 新过滤后 |
|---|---:|---:|---:|
| scope SYN-REVIEW（总出现数，指标排除） | 5 | 5 | 5 |
| model SYN-REQUIRED | 4 | 0 | 0 |
| model SYN-HS | 1 | 0 | 0 |
| model SYN-AMOUNT | 4 | 0 | 0 |
| model SYN-ORIGIN | 5 | 1 | 0 |
| model PUB-CN-DECLARATION | 4 | 2 | 2 |
| model PUB-US-INVOICE | 4 | 2 | 2 |
| deterministic extras | 0 | 0 | 0 |

剩余4对均公开资料建议（sample1/18），并非已证明的事实 FP，不能为追求 extra=0 随意删去。新 run unsupported finding=1、duplicate finding=2、duplicate citation removal=0。严格字段字符串 exact-match 有5处差异（invoice_no1、goods_description3、consignee1）；不影响本五例实际条件一致性，不代表提取达到全字段准确。

### 计时（5例，ms，nearest-rank）

| 阶段 | P50 | P95 | max |
|---|---:|---:|---:|
| upload→提取完成 | 2196 | 2852 | 2852 |
| upload→review/report 完成 | 6080 | 7321 | 7321 |

这是单机、合成数据、N=5 的一次观察；模型输出有随机性，不能把前后差异当因果/显著性或生产 SLA。计数 transport 共用 HTTP 连接池，计时也不能直接当成部署客户端性能。没有 chat 延迟数据。提示词不能纯离线验证；本次仅有上述一次五例真实验证；输出过滤/计数 replay 完全离线。

## 命令与验证

以下命令中 wrapper 仅读取指定私有配置注入 child env；输出删除 DSN/URL 行、脱敏 key/secret/password，不打印配置值。**付费命令已经执行一次，不要再次运行。**

```sh
# cwd: backend (唯一一次付费五例，wrapper 只设置 RUN_PROMPT_FIVE_E2E)
python3 /workspace/competition/backend-review-summary-prompt-evidence/run_five_private.py
# 实际 child: python -m pytest -q --tb=short -p no:cacheprovider tests/test_prompt_five_capture.py

# cwd: backend；只读账本，不联网
python -m eval.audit_summaries --capture ../reports/evidence/backend-eval-model-fp/live --output ../reports/evidence/backend-review-summary-prompt/previous-summary-audit.json
python -m eval.compare_prompt_five --previous ../reports/evidence/backend-eval-model-fp/live --current ../reports/evidence/backend-review-summary-prompt/live-five --output ../reports/evidence/backend-review-summary-prompt/five-comparison.json

# cwd: repository root；ruff binary: live-deepseek-71311f4-src/backend/.venv/bin/ruff
ruff check backend
# cwd: backend；全部 RUN_* 清空，DeepSeek/Qwen key 删除，注入真实 PG/Redis
python3 /workspace/competition/backend-review-summary-prompt-evidence/run_regression_private.py
# cwd: repository root
bandit -r backend/app backend/eval -q -f json -o /workspace/competition/backend-review-summary-prompt-evidence/bandit.json
gitleaks dir . --redact --no-banner --report-format json --report-path /workspace/competition/backend-review-summary-prompt-evidence/gitleaks-worktree.json
# 最终提交后
gitleaks git . --redact --no-banner --log-opts='c8c9a00..HEAD' --report-format json --report-path /workspace/competition/backend-review-summary-prompt-evidence/gitleaks-range.json
python3 /workspace/competition/backend-review-summary-prompt-evidence/verify_key_absent.py
```

验证结果：ruff **通过**；全量真实 PG/Redis 回归 **430 passed, 7 skipped，99.08s**（所有付费 opt-in 均跳过）；定向离线 **24 passed，0.06s**；唯一付费五例 **1 passed**。Bandit app+eval **0 findings**，Gitleaks worktree **0 findings**，真实 key 字节比较 **0 hits**；最终 commit-range 的回执外置保存。初次全回归发现新增离线 comparison 对“空 capture”的零计数归一化错误（428 passed / 1 failed / 7 skipped），已修复并增加缺失历史配对拒绝测试后无付费地重跑通过，保留初次回执。历史20条正文缺失限制由 `previous-summary-audit.json` 明确记录，不隐瞒。

证据：`reports/evidence/backend-review-summary-prompt/`（便携账本、same-five 比较、历史摘要审计、重启快照、README/SHA256SUMS）；原始新证据 `/workspace/competition/backend-review-summary-prompt-evidence/`；运行 harness 证据见 A。提交 hash、最终 commit-range 扫描回执与 bundle SHA256 由交付消息/外部回执提供，避免自引用校验和。
