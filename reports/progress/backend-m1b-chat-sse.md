# M1b 追问历史与 SSE

- 日期：2026-11-05（America/Tijuana）。
- 分支：`feat/backend-m1-pipeline`；原联调基线 `8d94e02`，本轮在 `c081f2c` 之上开发；bundle 相对 `main=d3c0b09`。
- 范围：历史、JSON 追问、SSE 事件、断线恢复、鉴权/CSRF、脱敏、引用校验、审计、按用户限流与明确错误。没有修改报告主链路的 L3 回退语义。
- **真实模型验收仍阻塞**：本轮不重试模型下载，不换镜像/改 DNS/绕过网络，不收集或记录密钥，不 `git push`。没有新增实际模型身份+真实成功调用+对应报告的验收证据。

## 实现与契约（OpenAPI 0.3.3）

1. `chat_messages` 用 M0 `create_all` 建表，保存 review_id/tenant_id/stream_id 和 ChatMessage 字段；用户、助手都入库，仅保存脱敏正文，映射不落库。GET 历史升序，权限与审查相同。
2. POST 默认/JSON 返回完整已保存的助手消息；输入提示注入/跨案件越权意图拦截为 HTTP 200 blocked=true + block_reason，保存用户与拦截消息、记审计，不调模型。
3. SSE 事件 `delta` → `citation` → `done`；错误用 `error` (Problem)。每事件 ID 为 `<stream UUID>:<递增序号>`；心跳是注释、不占 ID。blocked 输入仅发送 blocked=true 的 done。
4. **无可用模型**：JSON HTTP **503 MODEL_UNAVAILABLE**；SSE HTTP 200 后仅 **error**（Problem.status=503），无 delta/citation/done，无伪造助手成功消息。超时、截断、空回答、不安全输出和非法引用也失败关闭。
5. **恢复**：Last-Event-ID 从下一事件重放并跟随同一生产任务，不重复模型调用或消息；绑定原用户+租户+审查及相同问题/语言。首事件前可用响应头 X-Chat-Stream-ID + `:0`。已完成流重放剩余；终态已确认则空 SSE。无效/超前游标 422，问题不同 409，流过期/越权 404 后读取历史，不自动重新发起问题。
6. Redis 事件缓冲默认 900 秒，事务 WATCH/MULTI 保护游标递增和单一终态。生成任务独立于 HTTP 连接，断线不取消；正常关闭取消并记 error；异常进程退出的悬挂流在生成时限+5秒后持久化 error，绝不启动替代生成。
7. ProviderChain 的 chat_stream 实际请求上游 stream=true；仅首个上游正文 delta 前可重试/切提供方，部分回答失败后不混流。要求完整 stop + [DONE]；无模型不使用规则引擎补正文。
8. 上下文含当前 summary/findings、最近 12 条未拦截历史与本地 RAG，出域前统一脱敏；引文必须来自本次召回且 RuleIndex 存在，provenance 由 `RuleIndex.citation()` 重建（不信任模型提供 URL/日期）。
9. 审计 chat.message/chat.blocked/model.call/security.pii_masked/security.output_blocked，不含聊天原文、提示词、响应原文或密钥。默认每用户 20 次/分钟（含恢复请求），90 秒生成时限、12000 字符输出预算。
10. 删除单证时同步清理派生聊天与 Redis 回放，并取消本进程对应生成任务。

## 自动化证据与复现

- 明确标记的 `tests/fakes.py`：provider=`fake` / model=`test-fixture-only`，仅测试装配使用；正文也含 TEST FIXTURE ONLY。生产无 fake 开关。
- `tests/test_m1_chat_sse.py`：32 项，覆盖空/非空历史、JSON、SSE 次序/游标/来源、已完成与进行中恢复、HTTP 断开、输入拦截、生产无密钥明确失败、CSRF/Origin、未登录/角色/跨用户/跨租户、游标绑定/过期、脱敏与历史上下文、不安全分片/非法引用/截断/异常/超时、限流/CORS、worker 异常与正常关闭、上游协议及不混流。
- `tests/test_m1_pipeline.py`：旧 messages 501 断言改为实际成功，报告二次语言仍 501；新增单证删除时聊天/回放清理测试。
- httpx MockTransport 上游协议测试是手写 fixture，**不是真实模型证据**。

```bash
cd backend
uv run --offline ruff check app tests
uv run --offline ruff format --check app tests
uv run --offline pytest -q
cd ..
/tmp/oav/bin/python - <<'PYVALIDATE'
import yaml
from openapi_spec_validator import validate
with open('docs/api.yaml') as f:
    validate(yaml.safe_load(f))
PYVALIDATE
bash scripts/security-scan.sh
```

结果：ruff check/format 通过；OpenAPI 0.3.3 验证通过；全量 **142 passed / 1 skipped**（跳过的仍是真实 Ollama E2E）；安全扫描 **CRITICAL=0/HIGH=0/MEDIUM=0/LOW=0，ERRORS=0**。初次扫描发现一处 Semgrep 对 YAML 行内未加引号中文的解析错误，改为带引号文本后完整重扫通过，未忽略扫描器错误。

## 关键文件

- `backend/app/services/chat.py`：上下文、安全校验、生成任务、Redis 游标/恢复、落库与审计。
- `backend/app/api/v1/reviews.py`：GET/POST 追问；`documents.py`：派生聊天删除。
- `backend/app/db/models.py`：ChatMessage；`app/ai/types.py`：TextChunk/ModelUnavailable。
- `backend/app/ai/llm/__init__.py`：真实流式协议与一次性文本接口。
- `backend/app/main.py`、`core/config.py`：生命周期、CORS 与限流/超时配置。
- `backend/tests/test_m1_chat_sse.py`、`tests/fakes.py`、`tests/test_m1_pipeline.py`。
- `docs/api.yaml`、`backend/README.md`、`reports/security/2026-11-05.md`。

## 已知限制

- **真实 LLM 身份/调用/报告尚未验收，不以 fake 或规则回退替代。**
- 为避免跨 token PII/注入泄露，完整模型回答先校验，再发送 80 字符 SSE 段；有完整生成首字延迟，**不是实时 token 透传**。
- Redis 是短时回放，不是 durable job queue；进程异常只记/返回明确 error，不接管生成。DB 与 Redis 不做跨存储原子事务；极端故障应以 GET 历史为准，不自动重新生成。
- 历史 GET 暂无分页，模型只看最近 12 条；并行问题不做会话级排序锁。正则脱敏/注入与引用 ID 检查不等于法律正确性或完整安全保证。
- 报告二次语言仍 501；公开摘要仍不等于法规原文、完整适用性证据或合规通过。

交付：`/workspace/competition/bundles/feat-backend-m1b-chat-sse.bundle`，以 `main..feat/backend-m1-pipeline` 创建，前置提交要求 `d3c0b09`；未推送、未发群。
