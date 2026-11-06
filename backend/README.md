# 丝路智审 · 后端

FastAPI + PostgreSQL(pgvector) + Redis + arq，OCR 用本地 RapidOCR（PP-OCRv4 ONNX）。接口契约见 `../docs/api.yaml`，架构见 `../docs/architecture.md`。

## 一键启动（Docker Compose）

```bash
cp .env.example .env          # 在仓库根目录；按注释生成并填写 JWT_SECRET、DATA_KEK、数据库与 Redis 密码、初始管理员密码
docker compose up -d --build
curl http://127.0.0.1:8000/api/v1/readyz
```

本地大模型（M1 起用）：`docker compose --profile local-llm up -d`。

创建其他账号（密码交互输入，不进命令历史）：

```bash
docker compose exec api python -m app.cli create-user --username reviewer1 --role reviewer
```

## 本地开发与测试

```bash
cd backend
uv sync
uv run ruff check app tests
uv run pytest -q          # SQLite + fakeredis + 真实 RapidOCR，不需要 Docker
```

项目固定 Python 3.12（`.python-version`，RapidOCR 1.x 不支持 3.13），Docker 的 uv 与生成锁文件工具版本对齐。

`requirements.txt` 由 `uv export --frozen --no-dev --no-emit-project` 从 `uv.lock` 导出，供依赖漏洞扫描使用；改依赖后请重新导出。

## 安全要点

- 浏览器会话令牌在 HttpOnly + Secure + SameSite=Strict Cookie 中；写请求需会话绑定的 `X-CSRF-Token` 和白名单 Origin/Referer。
- 密码 Argon2id；登录限流 + 连续失败锁定；刷新令牌轮换与重放检测。
- RBAC（admin / reviewer / auditor）+ 对象级授权，越权访问返回 404 并记审计。
- 上传文件校验魔数、拒绝含脚本的 PDF、限制大小与页数；落盘 AES-256-GCM 信封加密。
- 审计日志哈希链，`/api/v1/audit/verify` 可定位被篡改的记录；演示篡改端点仅在 `DEMO_MODE=true` 时存在。

## M1 主链路与联调

上传后依次经历 `ocr_running → extracting → ready`；OCR → 注入检测（命中则拦截整个数据区）→ PII 脱敏 → 结构化 LLM 抽取 → Pydantic 校验 → 内存还原 → OCR 文本证据定位。字段与审查输入快照使用原件 DEK 加密保存，脱敏映射从不落库/进审计。

- `GET /api/v1/documents/{id}/recognition` 返回字段、真实坐标、调用轨迹、安全事件、AIGC 标识及 `degrade_level` 扩展字段。
- `PATCH /api/v1/documents/{id}/fields`：`{"version":1,"fields":[{"key":"hs_code","value":"123456"}]}`；CAS 乐观锁，旧版本返回 409；不伪造原件坐标；仅审计字段名和版本。
- `POST /api/v1/reviews`：`{"document_ids":["<document-id>"],"destination_country":"VN","language":"zh-CN"}`；202 后轮询 `GET /api/v1/reviews/{id}`，状态 `completed` 时有风险项、条款、摘要和模型轨迹。输入冻结在创建时的字段版本；修改原件字段不会偷偷改变旧报告。
- 审查先跑确定性规则，再本地召回/重排，最后 LLM 推理。只允许引用本次召回的规则 ID；非法引用被删除并标 `llm_unverified`。LLM 不能覆盖确定性规则发现的高风险。
- `GET /api/v1/reviews` 分页，`GET /api/v1/rules/{rule_id}` 可展开条款；租户和本人权限检查始终在服务端。
- 所有 `/api/v1` 示例均是 HTTP 路径；浏览器须通过 **HTTPS** 同站代理访问。容器 8000 只绑定回环，HTTP 仅供内网健康检查。

### Cookie / CSRF（含来源和会话绑定）

保持 `COOKIE_SECURE=true`、HttpOnly、SameSite=Strict。本地也配置自签 HTTPS 或本地 HTTPS 反代，不以关闭 Secure 解决联调问题。前端与 API 应使用同一 hostname（不要混用 localhost 与 127.0.0.1），`credentials: 'include'`。

1. `CORS_ORIGINS` 使用浏览器的完整 Origin（协议、主机、端口），不要填路径或通配符。
2. 登录也要求白名单 Origin（缺失时可回退同白名单 Referer）。
3. 所有 Cookie 会话写请求回传 `X-CSRF-Token`，值取 `csrf_token` Cookie。它是服务端 HMAC 签名的双提交值，绑定当前 access 和 refresh 会话；伪造同值 Cookie+Header、换会话复用或不允许的 Origin 均返回 403 `CSRF_FAILED` 并记审计。
4. 刷新时无需未过期的 access Cookie，但须与 refresh 绑定的合法 CSRF。每次登录/刷新后重新读取 CSRF Cookie，旧值不可用于新会话。
5. CLI 若手动发送 Cookie，也要发送白名单 Origin 和 CSRF；纯 Bearer 请求不带 Cookie 时不受浏览器 CSRF 影响。不要把令牌复制进前端存储。

### 模型配置与真实降级

`.env.example` 提供全部变量说明，密钥只填未入库 `.env`。链路默认 DeepSeek (`deepseek-chat`) → DashScope Qwen (`qwen-plus`) → Ollama (`qwen2.5:7b`)；使用 `httpx` OpenAI 兼容 JSON 接口，固定输出 schema、温度 0、token 上限、短超时、最多一次默认重试，连续失败熔断 60 秒。不记录提示词、完整响应或密钥。

- L0：主云端成功；L1：备用云端；L2：真实本地 Ollama；L3：全部不可用，启发式抽取部分字段 + 确定性审查，明确标规则模式。**L3 不是 LLM 成功，不适合宣称完成两类模型的现场演示。**
- Ollama 可选 profile 启动后须预先准备 `qwen2.5:7b` 权重。没有权重会真实失败并降级，不在请求时自动下载。
- `/system/models` 探测云端 `/models` 或 Ollama `/api/tags` 中的实际模型；15 秒缓存，超时默认 1 秒。该探测证明可访问和模型清单，不等于完成一次生成；实际推理成功/失败由任务轨迹和审计体现。API 从审计读取 worker 的最近 24 小时调用计数、P95 和近期连续失败，不伪造进程内指标。
- 默认 embedding 是确定性 `feature-hash-128`，reranker 是 `token-overlap-v1`，真实执行但**不是神经网络 BGE 模型**，接口与轨迹明确标注 lightweight/not BGE。
- 重型模型是可选 extra：`uv sync --extra bge`，提前离线缓存 `BAAI/bge-m3` 与 `BAAI/bge-reranker-v2-m3` 后设 `HEAVY_MODELS_ENABLED=true`。懒导入且 `local_files_only=True`、禁远程代码，不会让普通 `uv sync` 拉数 GB 权重。加载失败如实暴露 `heavy_load_failed=true` 并使用明确命名的轻量实现。Docker 默认镜像不安装此 extra；需自行构建带缓存的演示镜像。

### 规则库与当前边界

`backend/data/rules/*.json` 启动时建内存索引并分块；API/worker 各持只读副本。现同时加载两个分离文件：`synthetic-trade.json` 的 6 条 SYN 测试规则，以及 `public-trade.json` 的 5 条公开出处摘要（中国原产地条例、海关法、两用物项条例、WCO HS 体系说明、美国 19 CFR 141.86 发票要求）。每条公开记录带官方/权威 URL、对应条号、司法辖区及 `verified_at`；只用短摘要，不复制完整法律文本。2026-11-05（America/Tijuana）已核对页面内容可访问，启动时不联网，不保证链接/法规持续有效。

**前端必须展示以下字段，不能仅在开发者日志里保留：**

- Recognition 和 Review 的 `security.rule_corpus`：`synthetic`=仅合成/未核验/无引用，`mixed`=含合成和公开出处，`public_verified`=本次引用非空且全部是已核验公开出处。Recognition 表示配置索引范围，Review 表示实际召回上下文与确定性检查引用的并集；排队中和旧记录保守标 synthetic。
- `security.rule_corpus_label` 为可直接展示的中文标签；`security.retrieval_mode` 为 `lightweight_hash` 或 `bge`，轻量意味着 **非 BGE 神经模型**。
- `security.compliance_disclaimer` 固定为「自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。」；报告摘要也以语料标签和免责声明开头。
- 每条 citation 保留原始 source/jurisdiction、`corpus`、核验日期与 URL。SYN 规则始终保留「合成」与 SYNTHETIC，不改变 `determined_by=rule/llm` 的含义。
- `/system/models` 的 embedding/reranker 提供 `lightweight`、`implementation_mode` 和中文 `mode_label`；`healthy=true` 只证明当前实现可运行，不表示在用 BGE。

`public_verified` 仅表示**公开出处可追溯**，不是法律意见、现行性保证或适用性判断。WCO 是体系说明，不是目的国申报规则；美国发票规则不得套到其他目的国。确定性检查仍为合成测试规则，并总附 SYN-REVIEW，所以当前正常报告预期为 mixed 或 synthetic，绝不能宣称真实清关结论。

仍未实现：已有报告二次翻译，显式返回 501；新建审查可要求 LLM 生成指定语言，但规则引擎固定中文解释，L3 不伪装多语种生成。保留 M0 `create_all`，新增表可自动建，Alembic/RLS、跨进程全局熔断和每日 token 配额不在本次交付内。正则脱敏/注入检测只是防护一层，不保证任意姓名或混淆攻击全覆盖。

### 追问历史与 SSE（M1b，契约 0.3.3）

- `GET /api/v1/reviews/{id}/messages` 返回 `{items: ChatMessage[]}`，按创建时间升序；消息与审查相同租户/owner 权限。用户和助手消息都存 `chat_messages`（M0 `create_all`），仅存脱敏文本，不存映射；注入/越权意图拦截消息带 `blocked=true` 和原因并审计，**不调用 LLM**。
- `POST /api/v1/reviews/{id}/messages` 请求 `{"content":"解释此风险项","language":"zh-CN"}`；须 `chat_write`、Cookie CSRF/Origin 与已完成报告；默认每用户每分钟 20 次。结合脱敏 summary/findings、最近 12 条历史和 RAG，引用来自当前召回的真实规则 ID，所有 provenance 原样取 `RuleIndex.citation()`。
- JSON 模式成功返回完整 ChatMessage。**没有可用模型、超时、截断或输出/引用验证不通过：HTTP 503 `MODEL_UNAVAILABLE`，不造规则回退助手正文。** 用户问题保留在历史，失败没有助手成功消息。
- `Accept: text/event-stream` 用 fetch POST：事件 `delta` (`{"text"}`) → `citation` → `done`（完整已存消息）；失败只发 `error`（Problem，status=503、MODEL_UNAVAILABLE）并终止，HTTP 状态仍 200，**前端不能只凭 HTTP 200 判成功**。拦截输入仅 `done`（blocked=true），没有生成 delta。每事件带 `id: <stream UUID>:<序号>`，注释心跳不占 ID。
- 生产 ProviderChain 实际请求上游 `stream=true`；**完整回答先安全校验，再发送 80 字符分段的 SSE**，防止 PII/注入跨 token 泄露；不是实时首 token 透传。只能通过包含完整 stop + [DONE] 的上游流进入成功路径；首 delta 后失败不混入其他提供方的正文。
- 断线恢复：重发相同 POST URL/content/language、Cookie 与 CSRF/Origin，`Last-Event-ID` 填最后事件 ID（首事件前可从 `X-Chat-Stream-ID` 响应头取 ID，加 `:0`）。Redis 回放默认 900 秒，恢复只跟随原任务，不重入库/重调模型；done/error 已确认则空 SSE。流绑定发起用户+租户+审查；错误/超前游标 422，问题不一致 409，过期/越权 404 后应读取历史，不能自动重发问题。CORS 已允许 Accept/Last-Event-ID 并暴露流 ID 头。
- 连接断开不取消生成，正常关机取消并记 error。**进程崩溃没有 durable job 接管**，等待生成时限+5秒后返回 error，不重启生成；已入库历史仍可读。默认生成时限 90 秒、输出 12000 字符；`RL_CHAT_PER_MIN`、`CHAT_REPLAY_TTL_S`、`CHAT_GENERATION_TIMEOUT_S`、`CHAT_MAX_OUTPUT_CHARS` 可调整。删除单证时也清理派生聊天与回放。
- 自动化 `tests/test_m1_chat_sse.py` 明确使用 `provider=fake / model=test-fixture-only` 或 httpx fixture transport，**都不是真实模型验收证据**。当前真实模型验收仍阻塞：本轮没有重试下载/更换镜像/改 DNS，也没有网络绕过；实际模型身份+真实成功调用+对应报告的证据仍单独待验。

### 离线验证

`uv run pytest -q` 包括 M0 真实 RapidOCR、M1 FakeLLM+真实 OCR 主链路、手写 HTTP fixture 回放、降级/熔断、引用校验、规则召回、手工字段 CAS、跨租户/RBAC、PII 和 CSRF 攻防。FakeLLM 仅在 `tests/`，生产装配没有 mock 开关，不可以测试回放充当现场真实处理。

```bash
# backend 目录
uv lock
uv export --frozen --no-dev --no-emit-project -o requirements.txt
uv run ruff check app tests
uv run ruff format --check app tests
uv run pytest -q
# 仓库根
scripts/security-scan.sh
```


扫描脚本同时检查未提交工作区和 Git 历史（gitleaks），Bandit 排除虚拟环境但不跳过应用源码；扫描器报错会使整次验收失败。Python 漏洞审计针对 uv 导出的完整精确版本集合，使用 `--no-deps --disable-pip`，不再让系统 Python 3.13 重新安装 3.12 的 RapidOCR 依赖。此模式没有省略 uv 已锁定的传递依赖。

### 无云密钥：本机 Ollama 最小真实联调

安装与运行参考 [官方 Linux 指南](https://docs.ollama.com/linux)。安装包也可解压至用户自有工具目录，不需要 Docker/systemd；只绑定回环地址，不暴露无鉴权模型服务：

```bash
# 终端一，已安装官方 ollama
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 ollama serve
# 终端二
OLLAMA_HOST=127.0.0.1:11434 ollama pull qwen2.5:1.5b
curl http://127.0.0.1:11434/api/tags
```

仅在未入库 `.env` 填写以下非秘密配置（Pydantic 列表使用 JSON，不是裸 `ollama` 字符串）：

```dotenv
LLM_PROVIDER_CHAIN=["ollama"]
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b
LLM_TIMEOUT_S=120
LLM_MAX_RETRIES=0
HEAVY_MODELS_ENABLED=false
COOKIE_SECURE=true
```

宿主机 API 使用 127.0.0.1；Compose 内则用服务名 `http://ollama:11434`。其余 DB、Redis、KEK/JWT、管理员配置照 `.env.example`，从 backend 启动时显式加载根目录 `.env`（如 `uv run uvicorn app.main:app --env-file ../.env`）。浏览器仍经 HTTPS 同源代理并携带会话绑定 CSRF/Origin。

可在没有 Postgres/Redis 的开发盒运行条件真实链路（SQLite + fakeredis 仅替代基础设施，**不替代 OCR/LLM**）：

```bash
cd backend
RUN_OLLAMA_E2E=1 OLLAMA_BASE_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen2.5:1.5b \
  REALPATH_RESULT_FILE=/tmp/st143-realpath.json uv run pytest -q -s tests/test_m1b_realpath.py
```

该测试生成一张无个人信息的测试发票图片，实际通过 HTTPS ASGI 上传 API → 真实 RapidOCR → 真实 Ollama 字段抽取 → 本地召回/重排 → 真实 Ollama 推理 → reviews API。断言两次模型调用成功且 L2，失败不自动切 Fake；普通 pytest 默认跳过此需本机服务的慢测。输出文件只保留延迟、计数和模型轨迹，不含 Cookie/密钥/单证原文。它验证工程链路，不是法律准确率评测，也不等于 Docker/浏览器生产联调通过。
