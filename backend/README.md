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

`backend/data/rules/*.json` 启动时建内存索引并分块；API/worker 各持只读副本。当前 6 条 **SYN 合成审核规范**覆盖必填项、HS 格式、金额一致、原产地、合成禁限标记、人工复核提示，每条有 source/article/jurisdiction/url（合成条款无真实 URL，使用 null）。它们不是任何国家的正式法规、不是有效制裁名单，不能用于真实法律结论。正式比赛前须由统筹确定适用范围并替换为经核验的公开法规。

仍未实现：追问历史/POST/SSE 和已有报告二次翻译，显式返回 501；新建审查可要求 LLM 生成指定语言，但规则引擎固定中文解释，L3 不伪装多语种生成。保留 M0 `create_all`，新增表可自动建，Alembic/RLS、跨进程全局熔断和每日 token 配额不在本次交付内。正则脱敏/注入检测只是防护一层，不保证任意姓名或混淆攻击全覆盖。

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
