# 正式模型接入核查与真实推理验收状态

代码基线 `a437305`，分支 `feat/backend-llm-e2e`。本轮结果为 **受阻、未完成真实推理/SSE 成功验收**，不是验收通过。

## 接入与下载实测

- 正式实现支持 DeepSeek、Qwen、Ollama；本轮进程没有注入 DeepSeek/Qwen key，新工作树没有 `backend/.env`。仅核查当前任务配置范围，未搜索其它代理、账号或系统凭据，也未声称云端服务不可用。
- 本机 Ollama 回环 HTTP 可达，`GET /api/tags` 返回空模型列表。
- 对 `qwen2.5:0.5b` 仅尝试一次官方 `/api/pull`，约 64 秒后失败：权重重定向目标被拒，出现此前相同的非公网地址情况。立即停止；未换镜像、改 DNS/代理、换出口或绕过网络。未保存签名 URL、原始响应、模型输出或凭据。
- `availability.json` 只记录结构化脱敏结论。运行时 `m3-demo-env/runtime/test-environment.json` 未读取、未提交。

## `/api/v1/system/models` 与前端契约

`model-probe.json` 是实际 API 返回及 SSE 失败结果，不是手写假样例。此探测使用真实本机 Ollama HTTP，没有 FakeLLM、没有 HTTP mock；**数据库是 SQLite、队列/回放存储是 fakeredis**，审查上下文是合成记录，不等于本轮完成真实 PostgreSQL/Redis 全链路或真实模型推理验收。

- 顶层 `degrade_level=L3`，`llm_provider_chain=[deepseek,qwen,ollama]`；三项 LLM 的 `healthy=false`，云端 key 在此探测中明确不配置。
- OCR 可用不代表 LLM 可用。embedding/reranker 的 `healthy=true` 也不代表 BGE 已加载：应同时展示 `lightweight`、`implementation_mode`、`mode_label`，不能用 `configured_model` 冒充实际加载模型。
- 本轮 embedding 为 `lightweight_hash`，reranker 为 `lightweight_lexical`，均标明非 BGE。
- 无调用时 `p95_latency_ms=null`，`calls_24h=0`；不能呈现虚构延迟或调用数。
- `demo_mode=false` 时，无可用模型的追问 SSE 实际为 HTTP 200 打开事件流，随后仅 `event:error`，Problem `code=MODEL_UNAVAILABLE,status=503`；没有 `delta` 或 `done`。前端不能只按 HTTP 200 标成功。

## 未来可复现验收入口

新增 `RUN_MODEL_PROBE=1` 的实机空模型探测，验证 L3 和显式 SSE 错误；该测试通过只证明降级正确。

扩展既有 `RUN_OLLAMA_E2E=1`：真实 OCR → 字段抽取 → 报告 → SSE → 完成流回放。必须真实 Ollama trace、delta/done、无 error、无 fake，并完成回放，整体 `success` 才能为 true。输出仅模型元数据、计数、耗时，不含单证/对话原文。该成功路径因模型缺失本轮未运行，不能把代码已补齐写成真实验收成功。

具备模型后，在 backend 目录使用既有 Python 环境执行（模型名应为实际安装型号）：

```bash
RUN_OLLAMA_E2E=1 OLLAMA_BASE_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen2.5:0.5b REALPATH_RESULT_FILE=/tmp/real-llm-result.json python -m pytest -q tests/test_m1b_realpath.py
```

此既有入口的基础设施仍为 SQLite/fakeredis。真实模型验证与真实 PG/Redis 全栈验收需分别标记，不合并宣称。

## 本轮检查结果

- `RUN_MODEL_PROBE=1 ... pytest -q backend/tests/test_live_model_probe.py`：1 passed；真实空 Ollama 的 L3 和 SSE 显式失败探测通过，不是推理成功。
- 默认 `pytest -q`：277 passed，112 skipped（未注入本轮真实 PG/Redis 验收配置，及两个 opt-in 模型测试）；没有把这些 skip 写成通过。既有 M3 的活库证据不由此次默认回归替代。
- 本轮修改文件 Ruff check/format 与 `git diff --check` 通过。
- 安全扫描 HIGH=0、CRITICAL=0；详见 `reports/security/2026-11-06.md`，使用已有精确历史哈希误报忽略项，没有新增忽略规则。
- 未改业务 API、运行时配置、依赖或前端；只补验收测试及脱敏记录。真实推理与 SSE 成功路径仍未验证。
