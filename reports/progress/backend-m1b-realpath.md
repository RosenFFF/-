# M1b 后端：来源标识、公开语料与真实路径尝试

- 基线：`feat/backend-m1-pipeline`，HEAD `b6d4230`；仅工作区修改，未 commit、未 bundle、未 push。
- 记录时间：2026-11-05 17:37（America/Tijuana）。
- 结论：A/B 已完成；C 已尽力但**真实 LLM 推理未成功**，是官方模型下载被本机网络拒绝，不是仅以“缺密钥”作结。默认测试/Fake 路径通过，不以回放冒充真实推理。D 未实现，保留明确 501。

## 一、改动文件与接口约定

- `backend/app/services/provenance.py`（新增）：集中定义固定免责声明、语料分类及中文展示标签；仅 URL 存在不能提升为 public_verified，必须有人工核对元数据且不是 SYN/合成源。
- `backend/app/ai/types.py`、`services/fields.py`、`services/review.py`：Recognition、Review（含 queued/list/旧记录）始终返回非空的 `security.rule_corpus`、`rule_corpus_label`、`retrieval_mode`、`compliance_disclaimer`。报告 summary 开头加标签与免责声明，保留原 citation.source/jurisdiction 与 determined_by，不把 SYN 包装成法规。
- `backend/app/services/rag.py`：启动同时加载两份 JSON；citation 额外返回 corpus/verified_at；Recognition 标记配置索引范围，Review 按本次召回上下文及确定性检查引用并集保守标记。
- `backend/app/ai/runtime.py`：`/system/models` 的 embedding/reranker 加 `implementation_mode`、中文 `mode_label` 与统一 retrieval_mode，原 lightweight、configured_model、heavy_load_failed 保留。当前为「轻量回退（非 BGE 神经模型）」。
- `backend/data/rules/public-trade.json`（新增）：5 条公开出处短摘要，独立于原有 6 条 synthetic；不复制整篇法规或其中任何个人信息。
- `docs/api.yaml`：仍为 OpenAPI 3.1；来源字段列为必需，枚举及含义完整；补 Rule/Citation 核验信息和模型模式；标明 SSE/翻译 501 是当前实现，200 为后续目标契约。
- `backend/app/api/v1/reviews.py`、`tests/test_m1_pipeline.py`：追问 POST 明确返回 501「功能暂未实现：追问/SSE」，测试断言文案，不自动转 mock。
- `backend/tests/test_m1b_provenance.py`（新增）：来源字段、混合语料、保留 SYN 标识、旧记录回退、公开召回、伪 public 元数据、system 模式标签。
- `backend/tests/test_m1b_realpath.py`（新增）：显式 opt-in 的真实 RapidOCR→Ollama 抽取→RAG→Ollama 审查；没有 FakeLLM 或模型 HTTP Mock，失败指标也落脱敏记录。
- `backend/tests/conftest.py`：测试 Settings 不隐式读取 `.env`，避免本机真实联调配置污染离线测试。
- `.env.example`、`backend/README.md`：说明界面必须展示的字段、分类含义、适用范围边界、无 Docker Ollama 最小真实步骤、条件慢测。已有 `uv.lock`/精确 `requirements.txt` 保留，未新增应用依赖。
- `reports/progress/backend-m1b-realpath-attempt.json`：本次真实请求尝试的脱敏指标（失败，不含单证原文/模型原文/令牌/密钥）。
- `reports/security/2026-11-05.md`：按约定刷新当前工作区安全扫描报告。

### 前端必须直接展示

1. `security.rule_corpus`：`synthetic`=仅合成/未核验/空集；`mixed`=混入合成与公开出处；`public_verified`=引用非空且全为核验公开出处。
2. `security.rule_corpus_label`：中文可读标签；Recognition 指索引范围，Review 指本次实际上下文及规则检查引用，排队及旧数据保守标 synthetic。
3. `security.retrieval_mode`：`lightweight_hash`=哈希召回+词项重排（非 BGE）；`bge`=真正本地 BGE 实现。
4. `security.compliance_disclaimer` 固定值：**自动审查仅供人工复核；合成或未核验语料不得作为清关或交易决定依据。**
5. 模型页还可直接显示 `mode_label`。`healthy=true` 不意味着运行的是 BGE。

注意：确定性规则仍为 synthetic，并附 SYN-REVIEW，因此正常报告预期 mixed 或 synthetic。`public_verified` 仅是出处核验，不代表适用本票、现行性保证、法律意见或交易放行。美国发票规范不适用所有国家；WCO 页面为体系说明而非目的国完整申报细则。

## 二、公开语料及本次核验

2026-11-05（America/Tijuana）使用 WebFetch 逐一打开下列页面，内容可读取，并核对对应条款；不把搜索摘要单独当核验，不在启动时访问网页。

| ID | 覆盖主题 | 公开来源与定位 |
|---|---|---|
| PUB-CN-ORIGIN | 原产地证明/如实申报，明确非优惠范围 | [中国政府网：进出口货物原产地条例](https://www.gov.cn/gongbao/content/2019/content_5468935.htm)，第二、三、十一、十四、十八、二十六条 |
| PUB-WCO-HS | 六位国际 HS 基础，目的国扩展/版本需另核 | [WCO：What is the Harmonized System](https://www.wcoomd.org/en/topics/nomenclature/overview/what-is-the-harmonized-system) |
| PUB-US-INVOICE | 商业发票品名、数量、价格、币种、原产国及附件等 | [eCFR 19 CFR 141.86](https://www.ecfr.gov/current/title-19/chapter-I/part-141/subpart-F/section-141.86)，(a)/(d)/(e)，仅美国进口；动态权威电子文本非正式法律印本 |
| PUB-CN-DUALUSE | 公开管制清单/临时管制/许可/最终用户用途提示 | [中国政府网：两用物项出口管制条例](https://www.gov.cn/zhengce/zhengceku/202410/content_6981400.htm)，第十一至十四、二十一、二十四条；2024-12-01 施行 |
| PUB-CN-DECLARATION | 申报真实性及人工单证一致性核对提示 | [财政部关税司公开海关法](https://gss.mof.gov.cn/gszhs/falvlagui/202603/t20260313_3985268.htm)，第二十四、四十至四十二条 |

每条都有 id/source/jurisdiction/article/title/text/url/verified_at，正文为自写短摘要。未添加具体两用物项管制名录或实时制裁名单；未命中不能解释为允许出口。测试确认 RAG 至少召回一条有 HTTPS URL 的 public 规则。

## 三、本机配置检查与真实模型尝试（未成功）

### 配置核查（仅状态）

- 进程环境 `DEEPSEEK_API_KEY`、`QWEN_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_API_KEY` 均 unset。
- 检查 `/workspace` 与 `/workspace/competition` 下现有项目的标准 `.env`/`backend/.env`/`.env.local` 候选文件，仅解析上述字段是否 set；没有可用云密钥。未读取应用登录数据库、凭据文件或会话令牌，也未输出配置值。
- 起初无 Ollama 可执行文件、11434 无监听；约 15 GiB 内存、约 101 GiB 空闲磁盘；无 Docker，群聊 Vault 不可用已知不重试。

### 已尝试步骤及失败点

1. 按[官方 Linux 文档](https://docs.ollama.com/linux)下载官方 `ollama-linux-amd64.tar.zst` 至 `/workspace/tools/ollama-m1b/`。首次 tar 因系统缺 zstd 失败；用仓库外临时 Python zstandard 解压同一官方安装包成功，未改应用锁文件。
2. 安装版本 **Ollama 0.40.14**，以 `OLLAMA_NO_CLOUD=1`、单并发启动，**仅监听 `127.0.0.1:11434`**，CPU 模式。模型目录 `/workspace/tools/ollama-m1b/models`，未装 systemd 服务、未向外暴露端口。
3. 执行官方 `ollama pull qwen2.5:1.5b`，约 **64.7 秒后失败**：官方权重重定向到 Cloudflare R2，网络报告 `redirect target not allowed`，其域名解析到非公网 `198.18.0.1`。不保存/转贴带签名下载 URL，不绕过网络、不换镜像或伪造 DNS。
4. `/api/tags` 真实返回空模型列表。根目录本机 `.env` 已建、权限 0600、gitignore 确认命中：只写本地 Ollama 链路及 Secure/轻量配置，**无云密钥、无 JWT/KEK/账号密码**；不是完整生产启动配置。当前模型缺失会明确 L3。
5. 仍运行了一条真实上传→真实 RapidOCR→真实 Ollama 请求→reviews 的条件测试，确认没有 Fake 静默兜底。测试按设计拒绝把 L3 当通过；具体指标如下。

### 真实请求尝试指标

| 项目 | 实测 |
|---|---|
| 目标模型 | `qwen2.5:1.5b`（权重未拉取成功） |
| 真实推理成功 | **否** |
| 上传→OCR→审查总耗时 | **951 ms**（失败/降级路径，不是成功推理速度） |
| RapidOCR | 成功，283 ms |
| Ollama 字段抽取请求 | 失败，68 ms |
| Ollama 合规推理请求 | 失败，6 ms |
| recognition / review degrade_level | **L3 / L3** |
| 字段数 / 有 OCR 证据字段数 | 3 / 3，来自启发式规则，不是模型抽取成功 |
| 语料 / 检索 | mixed / lightweight_hash |

命令（backend 目录）：

```bash
RUN_OLLAMA_E2E=1 REALPATH_RESULT_FILE=/tmp/st143-m1b-realpath-attempt.json \
  uv run pytest -q -s tests/test_m1b_realpath.py
```

结果为 **1 failed（真实模型成功断言未满足，预期揭示当前缺口）**，不可宣称真链路验收通过。权重准备好后同一命令无需改代码；目标断言为真实 OCR、至少一个有证据的 LLM 字段、抽取和推理两次 Ollama 成功、L2 且无 fake provider。README/.env.example 提供完整最小步骤。

没有为了“跑绿”改用 Fake 作为真实路径；既有 FakeLLM 只用于离线回归。BGE 权重无本地缓存，本轮未下载/安装重型 extra，保留轻量模式并明确标识，未占用内存等待大模型。

## 四、验证结果

- `uv run ruff check app tests`：通过。
- `uv run ruff format --check app tests`：69 个文件已格式化，通过。
- 默认 `uv run pytest -q`：**106 passed, 1 skipped**；跳过项仅显式 opt-in 的本机 Ollama 慢测，Fake/安全攻防及真实 RapidOCR 回归通过。
- `/tmp/oav` 的 `openapi-spec-validator`：`docs/api.yaml` **OpenAPI 3.1 VALID**。
- `scripts/security-scan.sh`：HIGH=0、CRITICAL=0、MEDIUM=0、LOW=0，扫描器错误=0；semgrep、bandit、gitleaks（历史+工作区）、trivy、pip-audit、npm audit 均执行。最终结果见 `reports/security/2026-11-05.md`。
- `git diff --check`：通过；依赖未变化，保留现有 `backend/uv.lock` 和精确 `requirements.txt`。

## 五、已知缺口 / 下一步

1. **真实模型推理、BGE 实机召回和生产 Docker/浏览器联调仍未通过验收。** 当前只有真实 OCR 成功 + 真 LLM 失败降级，不满足以两类模型宣称完成现场处理的条件。
2. 准备官方模型权重后重跑条件测试；当前阻碍为本机网络拒绝官方权重重定向，不升级为“老板须提供云密钥”。
3. 前端需把新增 label/disclaimer 实际渲染并联合复测，单纯返回字段不等于 UI 已验收；本次未修改前端。
4. 公开语料只是有限可追溯摘要，不是完备法律知识库，未实现目的国适用性/法规变更全自动核验。现有确定性规则仍为 SYN 测试规则。
5. D 追问 SSE/历史未实现，POST 保持 501「功能暂未实现：追问/SSE」，已有报告翻译亦显式 501。没有自动切 mock。
6. Alembic/RLS、全局 token 配额、跨进程熔断等此前缺口未在本轮扩展。
7. 本机 Ollama 服务继续留在回环，便于后续排查；二进制/模型安装目录与 `.env` 均不进入仓库。需停止时终止本次 `ollama serve` 进程，不应误停其他服务。

建议提交信息：`feat(backend): expose rule provenance and seed traceable public corpus with real Ollama probe`
