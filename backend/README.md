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
# 宿主机先配置 DATABASE_URL（sqlite+aiosqlite:///... 或 postgresql+asyncpg://...）等环境；不在命令行写密码。
uv run --env-file ../.env alembic upgrade head
uv run ruff check app tests alembic
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

`.env.example` 提供全部变量说明，密钥只填未入库 `.env`。声明链路为 DeepSeek (`deepseek-chat`) → DashScope Qwen (`qwen-plus`) → Ollama (`qwen2.5:7b`)，但默认 `LOCAL_MODEL_ENABLED=false`，实际链路仅含云端；使用 `httpx` OpenAI 兼容 JSON 接口，固定输出 schema、温度 0、token 上限、短超时、最多一次默认重试，连续失败熔断 60 秒。不记录提示词、完整响应或密钥。

- L0：主云端成功；L1：备用云端；L2：真实本地 Ollama；L3：全部不可用，启发式抽取部分字段 + 确定性审查，明确标规则模式。**L3 不是 LLM 成功，不适合宣称完成两类模型的现场演示。**
- 只有显式设置 `LOCAL_MODEL_ENABLED=true` 且 `LLM_PROVIDER_CHAIN` 含 `ollama` 才允许 L2；默认完全排除 Ollama（不探测、不调用、不回退），云端均不可用直接 L3。该开关不影响本地 OCR、embedding、reranker；API 和 worker 须使用相同配置，配置变更后各自重启。
- Ollama 可选 profile 启动后须预先准备 `qwen2.5:7b` 权重。没有权重会真实失败并降级，不在请求时自动下载。
- `/system/models` 探测云端 `/models` 或 Ollama `/api/tags` 中的实际模型；15 秒缓存，超时默认 1 秒。该探测证明可访问和模型清单，不等于完成一次生成；实际推理成功/失败由任务轨迹和审计体现。API 从审计读取 worker 的最近 24 小时调用计数、P95 和近期连续失败，不伪造进程内指标。
- 默认 embedding 是确定性 `feature-hash-128`，reranker 是 `token-overlap-v1`，真实执行但**不是神经网络 BGE 模型**，接口与轨迹明确标注 lightweight/not BGE。
- 重型模型是可选 extra：`uv sync --extra bge`，提前离线缓存 `BAAI/bge-m3` 与 `BAAI/bge-reranker-v2-m3` 后设 `HEAVY_MODELS_ENABLED=true`。懒导入且 `local_files_only=True`、禁远程代码，不会让普通 `uv sync` 拉数 GB 权重。加载失败如实暴露 `heavy_load_failed=true` 并使用明确命名的轻量实现。Docker 默认镜像不安装此 extra；需自行构建带缓存的演示镜像。

#### 健康与每项能力的降级契约

- `GET /api/v1/system/models` 保留 `llm_provider_chain`（声明顺序）；新增 `local_model_enabled: bool` 与 `effective_llm_provider_chain: string[]`（实际参与的提供方顺序，不等于健康/已配置密钥）。默认分别为 `false` 和 `["deepseek","qwen"]`。
- 每个 LLM 行新增 `enabled: bool` 和 `disabled_reason: string|null`。Ollama 行始终显示：默认 `enabled=false, disabled_reason="local_model_disabled", healthy=false, circuit_open=false`；启用且在链内时 `enabled=true, disabled_reason=null`，健康状态由真实探测决定；启用但声明链未包含它时为 `false, "not_in_provider_chain"`。禁用行只是静态元数据，不调用 `_probe`。`calls_24h/p95_latency_ms` 仍可显示租户历史审计，不表示禁用后发生调用。OCR/embedding/reranker 行不受此开关影响。
- 顶层 `degrade_level` 和 `/readyz` 仅表示当前健康/可用性；不证明任何能力已执行，也不认证完整离线流程。所有级别选择都忽略禁用行。无 LLM 时核心依赖健康的 readyz 仍 HTTP 200、`status="degraded", degrade_level="L3"`。
- **UI 读取该能力自己的结果，而不是系统健康或另一能力的结果。** 识别字段和审查报告的 `degrade_level` 来自本次推理结果；规则回退为 `L3, degrade_status="规则引擎降级，需人工复核", llm_verified=false`。成功执行 Ollama 才为 `L2, degrade_status="本地模型", degrade_warning="完整离线流程尚未验收", llm_verified=true`；该 true 仅表示本次 LLM 执行成功，不是合规/完整离线验收。非 L2 的 `degrade_warning=null`。
- Chat JSON、SSE `done` 和历史助手消息新增同样四个降级字段，取自持久化的本次成功 LLM 轨迹 `degrade_level`，不从健康/审查状态推断。用户消息、安全拦截消息、缺少旧轨迹元数据的历史消息为 `degrade_level/degrade_status/degrade_warning=null, llm_verified=false`（未知/未执行，不冒充 L3 规则回答）。SSE `error` 与 JSON 503 `MODEL_UNAVAILABLE` 显式返回 L3 同组字段，保留现有「无可用 LLM，未完成真实/可用 LLM 验证」说明，**不会伪造规则引擎聊天回答**。重放/历史读取不重新调用模型。

### 规则库与当前边界

`backend/data/rules/*.json` 启动时建内存索引并分块；API/worker 各持只读副本。现同时加载两个分离文件：`synthetic-trade.json` 的 6 条 SYN 测试规则，以及 `public-trade.json` 的 5 条公开出处摘要（中国原产地条例、海关法、两用物项条例、WCO HS 体系说明、美国 19 CFR 141.86 发票要求）。每条公开记录带官方/权威 URL、对应条号、司法辖区及 `verified_at`；只用短摘要，不复制完整法律文本。2026-11-05（America/Tijuana）已核对页面内容可访问，启动时不联网，不保证链接/法规持续有效。

**前端必须展示以下字段，不能仅在开发者日志里保留：**

- Recognition 和 Review 的 `security.rule_corpus`：`synthetic`=仅合成/未核验/无引用，`mixed`=含合成和公开出处，`public_verified`=本次引用非空且全部是已核验公开出处。Recognition 表示配置索引范围，Review 表示实际召回上下文与确定性检查引用的并集；排队中和旧记录保守标 synthetic。
- `security.rule_corpus_label` 为可直接展示的中文标签；`security.retrieval_mode` 为 `lightweight_hash` 或 `bge`，轻量意味着 **非 BGE 神经模型**。
- `security.compliance_disclaimer` 固定为「自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。」；报告摘要也以语料标签和免责声明开头。
- 每条 citation 保留原始 source/jurisdiction、`corpus`、核验日期与 URL。SYN 规则始终保留「合成」与 SYNTHETIC，不改变 `determined_by=rule/llm` 的含义。
- `/system/models` 的 embedding/reranker 提供 `lightweight`、`implementation_mode` 和中文 `mode_label`；`healthy=true` 只证明当前实现可运行，不表示在用 BGE。

`public_verified` 仅表示**公开出处可追溯**，不是法律意见、现行性保证或适用性判断。WCO 是体系说明，不是目的国申报规则；美国发票规则不得套到其他目的国。确定性检查仍为合成测试规则，并总附 SYN-REVIEW，所以当前正常报告预期为 mixed 或 synthetic，绝不能宣称真实清关结论。

仍未实现：已有报告二次翻译，显式返回 501；新建审查可要求 LLM 生成指定语言，但规则引擎固定中文解释，L3 不伪装多语种生成。M2 已以 Alembic 替换 create_all；PostgreSQL RLS、跨进程全局熔断和每日 token 配额仍未实现。正则脱敏/注入检测只是防护一层，不保证任意姓名或混淆攻击全覆盖。

### 追问历史与 SSE（M1b，契约 0.3.3）

- `GET /api/v1/reviews/{id}/messages` 返回 `{items: ChatMessage[]}`，按创建时间升序；消息与审查相同租户/owner 权限。用户和助手消息都存 `chat_messages`（Alembic 初始迁移），仅存脱敏文本，不存映射；注入/越权意图拦截消息带 `blocked=true` 和原因并审计，**不调用 LLM**。
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
uv run ruff check app tests alembic
uv run ruff format --check app tests alembic
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
LOCAL_MODEL_ENABLED=true
LLM_PROVIDER_CHAIN=["ollama"]
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b
LLM_TIMEOUT_S=120
LLM_MAX_RETRIES=0
HEAVY_MODELS_ENABLED=false
COOKIE_SECURE=true
```

宿主机 API 使用 127.0.0.1；Compose 内则用服务名 `http://ollama:11434`。其余 DB、Redis、KEK/JWT、管理员配置照 `.env.example`，从 backend 启动时显式加载根目录 `.env`（如 `uv run uvicorn app.main:app_factory --factory --env-file ../.env`）。浏览器仍经 HTTPS 同源代理并携带会话绑定 CSRF/Origin。

可在没有 Postgres/Redis 的开发盒运行条件真实链路（SQLite + fakeredis 仅替代基础设施，**不替代 OCR/LLM**）：

```bash
cd backend
RUN_OLLAMA_E2E=1 OLLAMA_BASE_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen2.5:1.5b \
  REALPATH_RESULT_FILE=/tmp/st143-realpath.json uv run pytest -q -s tests/test_m1b_realpath.py
```

该测试生成一张无个人信息的测试发票图片，实际通过 HTTPS ASGI 上传 API → 真实 RapidOCR → 真实 Ollama 字段抽取 → 本地召回/重排 → 真实 Ollama 推理 → reviews API。断言两次模型调用成功且 L2，失败不自动切 Fake；普通 pytest 默认跳过此需本机服务的慢测。输出文件只保留延迟、计数和模型轨迹，不含 Cookie/密钥/单证原文。它验证工程链路，不是法律准确率评测，也不等于 Docker/浏览器生产联调通过。


## M2 安全与审计（契约 0.4.0）

**本交付不含真实模型验收。** 以下回归中的 FakeLLM/httpx transport 都是测试替身，不证明真实答案链路可用。

### 纵深过滤

- 输入检测增加 HTML 实体、全角/零宽归一化、伪造角色标签、关闭鉴权/审计等指令。OCR、手工字段、报告上下文、聊天历史及召回规则均不作为可信指令。
- 抽取/报告服务在供应方 JSON 校验之外再次检查嵌套文本，拦截敏感 PII、凭证格式、系统提示泄露/越权指令；被拒绝的报告明确 L3（保留确定性发现），不能混成真实模型成功。`security.output_blocked` 只记任务名，不记录正文。
- 追问完整缓冲后再校验；跨 token 的凭证/PII/注入/越权残留只产生 MODEL_UNAVAILABLE，不透传 delta 或伪造 done。输入拦截仍沿用 blocked=true 契约。
- 密钥/密码/Bearer/JWT/私钥格式在出域脱敏前剥离且不加入可还原映射。报告/历史/识别 JSON 和审计有读取防护，保护旧记录；合法语料文案和引用来源不做无意义归一化改写。授权原件图片仍为原始文件，不是 DLP 清洗后的图片。
- 正则仅为启发式防护，非完整 DLP/语义注入防御，可能误报/漏报；没有运行生成内容、工具调用或 SQL 的模型权限。

### 限流

所有已鉴权写请求先进入租户+用户总桶（`RL_DEFAULT_PER_MIN=300`）；上传、报告创建、追问（JSON/SSE/续传）还有独立租户+用户桶，默认分别 20/10/20 次每分钟。登录（包括失败）按真实连接 IP 默认 10 次，refresh/logout 共用 IP 桶默认 30 次；不信任客户端 X-Forwarded-For 改变 IP。反向代理须只信任实际代理网段，生产不可宽泛信任转发头。

- 可配置：`RL_LOGIN_PER_MIN` / `RL_UPLOAD_PER_MIN` / `RL_REVIEW_PER_MIN` / `RL_CHAT_PER_MIN` / `RL_AUTH_PER_MIN` / `RL_DEFAULT_PER_MIN`，正整数，不能以 0 悄悄禁用。
- 超限：429 `RATE_LIMITED`，`application/problem+json` + `Retry-After`（秒）+ request_id，审计 `rate_limit.hit`；SSE 限流发生于建立流之前，返回普通 HTTP 429。
- Redis 不可用：503 `RATE_LIMIT_UNAVAILABLE`，拒绝写入而非无上限放行。滑动窗口使用 Redis 事务，拒绝的请求不扩张有序集合，最多保存桶额度个成员。
- 不替代边缘层上传连接数/体积/匿名流量限制；请求体校验在接口限流之前完成，网关应另加连接与请求体配额。

### 审计 API

- `GET /audit/logs` 仅 admin/auditor，严格本租户；不再把 tenant_id=null 的平台/未知登录事件分享给所有组织。`action/result/actor_id` 精确匹配，`since` 含、`until` 不含；ISO 时间必须有时区且 since < until；page 从1开始，page_size 1–100，按 seq 倒序。拒绝访问的 reviewer 返回403并记审计。
- `GET /reviews/{id}/audit` 同租户、同案件读取权限；reviewer 只看本人案件，含关联单证轨迹；支持同一过滤/分页契约，越权404。
- `GET /audit/stats?window=1h|24h|7d`：只统计本租户已落库事件，含 totals、零值补齐的 UTC timeline、top_denied_actors、audit_chain_valid。requests=审计事件数（非 HTTP 请求数）；pii_masked=各类数量之和，tokens_used=tokens_in+tokens_out，model_fallbacks 包含回退调用，新增 outputs_blocked。不是实时 HTTP 监控或模型验收。
- `GET /audit/verify`：验证物理共享链中本租户记录的内容和相邻链接，仅返回本租户 checked/head/first_broken_id；不暴露外租户计数、ID 或断链。平台全链审计可通过内部 AuditService.verify() 完成，不对租户开放。没有外部签名锚点时，不能证明已删尾部未被整体重算。
- 审计 detail 写入前去密钥/PII/指令，读取旧记录也过滤；读取过滤不会修改历史记录或重写 hash，读出的已过滤 detail 不用于客户端重算原始哈希。平台无租户事件需另行受控平台运维查看；本接口不暴露。
- 统计按时间窗流式扫描审计行，内存有界；验证链为 O(N)，大规模部署应异步缓存/独立校验任务并加索引/分区，目前不是海量审计后端。

### Alembic 与已有数据库

初始版本 `0001_m2_initial` 静态冻结全部 11 张业务表、索引、外键（含 document_fields/review_documents/chat_messages），不导入运行时模型生成 DDL。JSON 在 SQLite 用 JSON，在 Postgres 用 JSONB；audit seq 在 SQLite 为 INTEGER，在 Postgres 为 BIGSERIAL。

- Compose 新增一次性 `migrate` 服务，先 `alembic upgrade head` 成功再启动 API；API、worker、create-user 只检查 revision，不执行 create_all/并发 DDL。容器已复制迁移目录。
- 宿主机先运行 `uv run --env-file ../.env alembic upgrade head`，再启动 API/worker。Alembic URL 只从 DATABASE_URL 或程序注入获取，不写入 ini，不输出带密码 URL。`ENV=test` 自动执行同一版本化迁移，所以普通 SQLite pytest 覆盖真实迁移路径。
- **已有 M0/M1 create_all 数据库**：先备份数据库与密文存储，停止写入；在副本上运行 `uv run --env-file ../.env python -m app.cli adopt-legacy-schema`。该命令比较 Alembic 支持的 schema 差异并额外校验每张表的主键；无差异且无已有版本才 stamp 到 head（不能替代人工审查数据库特有对象），不改业务表、不删数据；缺表/列/索引或已有版本会拒绝，需人工审查增量迁移。禁止不检查直接 stamp/删表重建生产库。验证备份可恢复后再在维护窗口执行。
- 新增模型/列后应创建新的静态 revision；不得改写 0001 或仅靠 metadata 更新。`alembic check` 检查 metadata 漂移。
- `tests/test_m2_migrations.py` 保留 SQLite 迁移往返、旧库接管及 PostgreSQL 离线 DDL。PG 活库往返已移到 `tests/test_m2_postgres_live.py`，与其余活库测试统一使用随机独立 schema；不再 downgrade 整个目标数据库。严格 opt-in、运行边界和本次环境阻塞见下节。

回归证据：`test_m2_security.py`、`test_m2_limits.py`、`test_m2_audit_isolation.py`、`test_m2_migrations.py`、`test_m2_openapi.py`；完整范围和数字见 `reports/progress/backend-m2-security.md`。

生产 env=prod 强制不注册 demo 路由，即使 DEMO_MODE 被误设为 true。


### 前端审计字段对齐（frontend @76830b2）

请求原文已复制到 `docs/backend-m2-audit-request.md`。看板新增 `window_start/window_end/generated_at`，totals 增加 `csrf_failed/auth_locked/model_errors`；timeline 补齐 `logins_failed/pii_masked/model_fallbacks` 及三项细分指标。时间均为 UTC ISO 8601，前端可自行转本地显示。

- `csrf_failed`：有合法、未过期 access 签名且当前用户可用的 CSRF 拒绝事件归入该用户租户；伪造/过期 Cookie、未知登录等无法可信归属的事件仍为平台私有，不凭 unsigned claims 分配租户。
- `auth_locked`：失败登录触发账号进入锁定状态的次数；锁定后每次重试仍计 `logins_failed`，不重复计一次新锁定。
- `model_errors`：失败的 `model.call` 事件（非 status=fallback）；它不是最终报告失败数，也不等于真实模型质量评估。tokens 来自轨迹，不做计费声明。
- 看板级 `degrade_status` 是「真实审计事件统计；模型事件已记录；未完成真实模型验收」，`llm_verified=false`。该字段表示**统计窗口缺少真实模型核对/验收证据**，不将普通模型成功轨迹或 FakeLLM 充当已验收。
- `source_kind=synthetic` 保守包括来源未核验（与现有语料标签约定一致），配 `source_kind_label` 明确「来源未核验 · 非真实模型验收」。它不声称 API 在读 mock：指标始终来自落库事件；没有事件时真实返回零计数。
- 每条 AuditLog 的 `detail` 使用显式 `AuditDetail` schema。`source_kind/source_kind_label/degrade_status/llm_verified/fallback_reason/injection_category/pii_fields/rate_limit_scope` 始终返回（不适用者 null）；同时镜像顶层 actor_role/resource_type/resource_id/ip。额外业务字段如 counts、模型轨迹仍保留。旧行按读取投影补齐，不重写哈希。
- `injection_category` 为 prompt / scope / output；不虚构 SQL/path 检测。`pii_fields` 是脱敏类别名（不是原文）；`rate_limit_scope` 为 ip 或 user（租户+用户），route 仅预留枚举。
- `fallback_reason` 可为 provider_fallback / model_error / unsafe_output；未发生或未知为 null。模型类行也保持 `llm_verified=false`；测试替身行明确标「测试替身/演示来源」。未核验不能自动推断为 public，也不会仅从 fallback 轨迹生成「真实主链路可用」标记。

DEMO_MODE 的篡改/恢复步骤与 fixture 说明见 `docs/backend-m2-demo.md`。reviewer 对 `/audit/logs`、`/audit/stats` 均为403并审计，admin/auditor 可读。本 API 已真实实现落库聚合，不用501/503假装占位；内部错误仍按统一 Problem 返回，不返回伪造成功。


### PostgreSQL 活库验收入口（环境阻塞，未验收）

**本次没有运行成功的 PostgreSQL 活库测试，也未实现 DB RLS。** 详见
`../reports/progress/backend-m2-postgres-live.md`。客户端版本不代表服务器已启动。

在具备真实本地 PostgreSQL 的隔离环境中：

1. 准备专用一次性数据库，名称须以 `st143_m2_test_` 开头；验收角色须为
   `NOSUPERUSER NOBYPASSRLS`，且能在该库 `CREATE SCHEMA`。不要使用生产/共享数据库。
2. 仅在本地未入库 env 文件中配置 `TEST_POSTGRES_URL`（优先）或 `DATABASE_URL`，
   PostgreSQL asyncpg URL；密码不进命令行、报告或聊天。只允许本地 loopback / Unix socket。
3. 在 backend 目录运行：

   ```bash
   TEST_POSTGRES_DISPOSABLE=1 uv run --env-file /path/to/local-test.env \
     pytest -q -rs tests/test_m2_postgres_live.py --junitxml=/tmp/st143-pg-live.xml
   ```

测试为每例创建随机私有 schema，通过连接的 `search_path` 隔离，结束只删除该 schema；
迁移和 API 使用真实 SQLAlchemy/asyncpg/PostgreSQL，不替换数据库。缺 URL 才 skip；
配置不安全、缺 opt-in、连接失败或角色有 SUPERUSER/BYPASSRLS 时必须 error/fail，不能假绿。
`tests/test_m2_postgres_target.py` 的 12 项是离线目标保护测试，**不是 PG 活库证据**。

活库模块 10 项：迁移到 `0001_m2_initial`、重复升级、metadata 零漂移、保留数据、
降级重升；同组织他用户与外组织 admin 的文档/报告/追问/续传/案件审计拒绝；
审计租户/NULL 事件隔离、过滤和分页；reviewer 403 与 admin/auditor 数据访问；
隔离 DEMO 的跨组织篡改/恢复拒绝。

其中 `test_postgres_current_rls_absent_raw_sql_bypasses_application_scope` 是**否定基线**：
查询 `pg_class` 确认 11 张表 RLS 未启用，设置外租户 GUC 后故意去掉应用 WHERE，
检查仍能用应用数据库角色直接读取其他租户文档、报告和审计。该例通过代表
「应用层过滤可被直接 SQL 绕过 / DB RLS 缺失」，绝不是 RLS 验收通过；本次也未运行。
将来落地 RLS 必须替换该基线，补 SELECT/INSERT/UPDATE/DELETE、未设置上下文、
提交/回滚和连接池复用的 fail-closed 验证，并保证 worker/审计共享链不被破坏。

基础设施/模型边界：这些 PG API 用例仍使用 fakeredis、快速 OCR fixture 与 FakeLLM；
只验证实际 PG 上的迁移和应用授权，不验证真实 Redis、OCR/LLM 主链路或生产部署。
真实模型验收继续单独阻塞。


### M2 租户上下文补强（仍未验收/不可部署）

本轮以 `reports/progress/backend-m2-tenant-context.md` 为当前证据，早期「尚未实现」描述只作历史记录。
迁移 head 为 `0003_m2_auth_audit_context`（前置 `0002_m2_tenant_rls`）：登录是 exact-username
只读凭证能力，不建立业务访问身份；成功验密后才解除 credential-only 限制。访问 JWT 先验签/UUID/角色、
绑定事务 LOCAL tenant scope 再查询 User；组织/角色漂移作废旧令牌。刷新 Cookie 变更为签名路由证明+nonce，
仅存哈希，旧不透明 Cookie 需重新登录。请求、ARQ/inline、SSE 均显式传递/重验租户，无全局 tenant ContextVar。

审计改为每租户独立 hash 链，平台事件独立 null 链；写入重验 actor org/role，后台失败也带完整归属。
**没有改写任何历史审计 hash**：旧共享链有外租户前驱时 verify 仍失败，必须另审历史归档/切换方案。
没有 PostgreSQL 活库通过证据，API 与 worker 启动门禁保持无条件阻止 PostgreSQL。
SQLite 的 scoped ORM 查询/写入防护不是 SQLite 数据库 RLS；显式 maintenance_sessionmaker/raw connection 仍是受信管理能力，
不能接给 API 请求。真实模型、真实 Redis、真实 PostgreSQL 的验收不能用 fakeredis/测试模型替代。
