# M1 后端执行器交付记录

- 分支：`feat/backend-m1-pipeline`；基线/当前 HEAD：`d3c0b09`。
- 仅修改本 worktree；未 commit、未创建 bundle、未 push，交给主会话审核提交。
- 验证时刻：2026-11-05 17:28:56（America/Tijuana）。

## 已实现

- OCR → 注入检测 → 出域脱敏 → LLM JSON schema 抽取 → 内存还原 → 证据定位 → 字段加密保存。
- DeepSeek / DashScope Qwen / Ollama 提供方链、超时、一次默认重试、熔断、L0–L3；无密钥不访问云端，全部不可用时真实启发式/规则兜底。
- 明确命名为非 BGE 的 hash embedding + lexical rerank；可选 BGE extra、仅本地缓存、禁远程代码；启动建合成规则索引。
- 确定性审查 → RAG 召回和精排 → LLM 推理 → 引用白名单校验 → 风险报告/AIGC。
- reviews POST/list/detail、rules detail；inline/arq；字段 CAS 修订、审计、不可变加密审查输入快照；删除原件清理相关快照/报告。
- `/system/models` 实时短超时探测，展示实际引擎及轻量/BGE 回退状态；从审计读取 worker 调用计数/P95/近期连续失败。
- CSRF HMAC 绑定当前 access/refresh 会话；Origin 白名单、缺失时 Referer 回退；伪造同值双提交和跨会话复用均拒绝并审计；生产默认 Secure 不放宽，联调要求 HTTPS。
- Python 3.12 固定、httpx 升为运行依赖、uv.lock 与哈希 requirements 导出、Docker 复制种子规则且 uv 版本与锁文件生成工具对齐。

## 验证

- `uv run pytest -q`：**94 passed in 31.53s**（M0 42 + M1 52）。包括 FakeLLM + 真实 RapidOCR 上传到报告主路径、合规引用、PII 内存还原和加密、注入拦截、RBAC/跨租户、CAS、实际 HTTP 回放/熔断/L3、CSRF/Origin 攻防。
- `uv run ruff check app tests`：通过。
- `uv run ruff format --check app tests`：66 files already formatted。
- `uv lock --check`：通过，112 packages；解释器 Python 3.12.15；app import 通过。
- `openapi_spec_validator`：`docs/api.yaml` **v0.3.0 通过**；修复 flow-style 中文/含逗号描述的引号，使 schema 描述不再被 YAML 拆成意外键。
- `git diff --check`：通过。
- `scripts/security-scan.sh`：exit 0，**CRITICAL=0 HIGH=0 MEDIUM=0 LOW=0 ERRORS=0**；semgrep、bandit、gitleaks（历史+未提交工作区）、trivy、pip-audit、npm audit 全部 OK，无跳过。报告：`reports/security/2026-11-05.md`。
- `.env` 未追踪；未填写或读取任何真实密钥；gitleaks 工作区与历史均无发现。

## 扫描脚本修复说明

原脚本会把 semgrep 解析警告和 pip-audit Python 3.13 安装失败当作 0 发现通过；Bandit 管道在 pipefail 下误跳过；gitleaks 原来只看历史。现将扫描器错误设为门禁失败，实际运行应用 Bandit，并补工作区密钥扫描。pip-audit 针对 uv 导出的完整精确版本集合使用支持的 `--no-deps --disable-pip`，不再由系统 3.13 重装仅支持 3.12 的 RapidOCR；没有减少传递依赖检查。

## 已知边界 / 下一步

- 没有真实云端密钥调用、Ollama 权重或真实 BGE 重型推理验收；未运行 Docker build/compose。离线测试绝不充当现场真实模型处理。
- 当前 6 条 SYN 规则是明确标识的合成测试规范，不是正式法规/真实制裁名单；正式演示前须替换/扩充经核验的公开法规。
- 默认轻量召回/重排不算真实 BGE。现场需要配置真实 LLM（或事先验证 BGE）满足至少两类模型；L3 明确仅规则，不伪称满足。
- 追问历史/POST/SSE、已有报告二次翻译显式 501；新建审查支持指定 LLM 语言，但确定性解释固定中文，L3 不假装生成多语种。
- 继续使用 create_all；Alembic/RLS、跨进程全局统一熔断、每日 token 配额未实现。API 通过审计显示 worker 熔断迹象，但各进程调用电路仍各自维护。
- 正则 PII/注入检测是多层防护的一层，不保证任意姓名或混淆攻击全覆盖。

## 建议提交标题

`feat(backend): implement secure M1 extraction and RAG compliance reviews`

## 改动文件清单（含新增）

- `.env.example`
- `backend/.python-version`
- `backend/Dockerfile`
- `backend/README.md`
- `backend/app/ai/embedding.py`
- `backend/app/ai/llm/__init__.py`
- `backend/app/ai/reranker.py`
- `backend/app/ai/runtime.py`
- `backend/app/ai/types.py`
- `backend/app/api/v1/documents.py`
- `backend/app/api/v1/reviews.py`
- `backend/app/api/v1/rules.py`
- `backend/app/api/v1/schemas.py`
- `backend/app/api/v1/system.py`
- `backend/app/core/config.py`
- `backend/app/db/models.py`
- `backend/app/main.py`
- `backend/app/security/cookies.py`
- `backend/app/security/injection.py`
- `backend/app/security/redact.py`
- `backend/app/services/document_access.py`
- `backend/app/services/field_edit.py`
- `backend/app/services/fields.py`
- `backend/app/services/model_health.py`
- `backend/app/services/pipeline.py`
- `backend/app/services/rag.py`
- `backend/app/services/review.py`
- `backend/app/services/rules_engine.py`
- `backend/app/workers/tasks.py`
- `backend/data/rules/synthetic-trade.json`
- `backend/pyproject.toml`
- `backend/requirements.txt`
- `backend/tests/conftest.py`
- `backend/tests/fakes.py`
- `backend/tests/fixtures/llm/extraction.json`
- `backend/tests/fixtures/llm/reasoning.json`
- `backend/tests/test_auth.py`
- `backend/tests/test_m1_llm.py`
- `backend/tests/test_m1_pipeline.py`
- `backend/tests/test_m1_security.py`
- `backend/uv.lock`
- `docs/api.yaml`
- `reports/progress/backend-m1-executor.md`
- `reports/security/2026-11-05.md`
- `scripts/security-scan.sh`
