# DeepSeek 真实链路验证（待审核，未合并）

## 结论

- 基线 main `8c42d49`；验证代码提交 `ca0ae4a`，分支 `feat/coord-llm-deepseek-e2e`。main 未改、未推远程。
- 用户授权的密钥仅经进程环境注入。最小 `deepseek-chat` completion HTTP **200**，837ms；API 可达、密钥有效。
- 真实端到端 **1 passed in 9.93s**。实际 DeepSeek + RapidOCR + 隔离 PostgreSQL 非 owner 运行角色/FORCE RLS + 实际回环 Redis；没有 FakeLLM、SQLite 或 fakeredis。
- `/system/models` 实测 `deepseek-chat healthy=true`、**L0**；`readyz` HTTP 200 / ready。OCR 健康，检索与重排仍是轻量回退，不能称 BGE。
- 上传/抽取 1347ms：3 个 OCR block、3 个有来源锚定的 LLM 字段，L0。
- 审查 4923ms：completed / L0 / `llm_verified=true`；共 6 条发现（2 rule、4 llm），7 个引用；无无效引用丢弃。语料混有合成规则，不是实际法律合规认证。
- 简短报告追问 SSE 1285ms：HTTP 200，1 delta + 1 done，0 error，31 字符，真实 DeepSeek trace；完整回放一致。另一用户读报告返回 404；审计链 valid，checked=16。
- 最终代码完整默认回归 **391 passed, 3 skipped in 103.79s**；三项 skip 是外部模型 opt-in（DeepSeek、Ollama、空库存探测），其中 DeepSeek 单独真实运行已通过。默认成功场景仍含测试替身，不冒充全部模型实测。
- Ruff check/format 通过；gitleaks 工作树无泄漏；Bandit app 扫描无发现。

## 发现与修复

官方 `/v1/models` 此次 HTTP 200 仅列出 `deepseek-flash`、`deepseek-v4-pro`，但 `deepseek-chat` completion 实际成功。原探针严格按列表匹配，首轮错误显示 L3。新增云端模型别名验证：仅在列表缺少配置模型时，调用一个 `max_tokens=1` 的真实 completion 验证，不凭别名猜测健康；维持原超时、15 秒缓存、门禁及输出控制。此额外探测会产生少量 API 使用量。加入成功/404/畸形响应/401及缓存回归测试。Ollama 仍严格检查库存，不发起此回退探测。

## 保留的失败，不隐藏

1. 初始未修复健康探针：1 failed，L3；在 `initial-alias-health-failure/`。
2. 修复后首个完整审查已成功（5 条 llm 发现），但问题 “What invoice fields should I verify next?” 的 SSE 只返回 `MODEL_UNAVAILABLE`，1 failed；在 `first-review-sse-error/`。底层官方 SSE 独立诊断为 HTTP 200、120 frames、585 字符、finish=stop、DONE=true，因此不能称网络或密钥失败；该问题的应用层失败具体原因尚未定位。
3. 最后通过的是不同的、简短报告问题 “In one short sentence, what destination country is this report for?”。这是成功通路验证，不是原问题修复，也不能据此宣称追问普遍稳定。未放宽安全检查、未改写旧证据。

## 范围与复现

- HTTP 使用 ASGITransport，后台任务 inline；不是浏览器、生产包或 ARQ worker 端到端彩排。单次样例，不是 P95、并发或稳定性认证。
- PG fixture 新建随机隔离 schema，迁移用 owner，应用用单独非 owner 角色；租户/startup 检查全部执行。Redis 使用本机已安装二进制启动独立回环实例，避免污染已有数据。
- 活库配置沿用私有 `/workspace/competition/m3-demo-env/runtime/test-environment.json`；不复制其值。密钥仅 source 已有私有 env 后运行：

```sh
# 在本分支工作树根目录；禁用 shell tracing，不输出环境变量
set +x
set -a
source /workspace/competition/secrets/deepseek.env
set +a
/workspace/competition/st143/backend/.venv/bin/python /workspace/competition/llm-deepseek-evidence-8c42d49/run_verification.py real
# 默认回归会从子进程移除云密钥和真实模型成功路径的开关
/workspace/competition/st143/backend/.venv/bin/python /workspace/competition/llm-deepseek-evidence-8c42d49/run_verification.py full
```

证据目录 `/workspace/competition/llm-deepseek-evidence-8c42d49/`：包含脱敏请求元数据、models-probe、readyz、realpath、pytest 输出、静态扫描和 SHA256SUMS。输出只含结果计数、来源与耗时，不保存模型原文、cookie、Authorization、原始密钥或数据库连接串。目录名标记基线，实际测试代码身份以 `verification-metadata.json` 为准。复跑前另建证据目录，避免覆盖本轮结果。

## 剩余事项

- 审核并合并别名健康修复；主线目前仍有该健康误判。
- 定位首个较宽泛追问的应用层 SSE 失败，增加多问题真实回归。
- 浏览器 + 生产包 + 真实模型 + PG/Redis 全链路彩排尚非本轮范围。
- 本地 Ollama 无模型的问题不影响此轮云端成功，但未因此获得本地模型成功证据。
