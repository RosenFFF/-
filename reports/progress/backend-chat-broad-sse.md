# 宽泛追问 `MODEL_UNAVAILABLE` 定位与真实 DeepSeek 多问题 SSE 回归（待审核）

## 结论

- 基线 main `aaee76a`，分支 `feat/backend-chat-broad-sse`。未推远程。
- **应用层根因**：追问的引用白名单只取"本次问题"检索出的 top-5 规则。宽泛追问会讨论报告自身的发现，模型正当地引用了报告发现里的规则（如 `SYN-ORIGIN`、`SYN-AMOUNT`），但它们不在这次问题的 top-5 中。严格校验于是把健康模型的完整回答整体判为失败，返回 `MODEL_UNAVAILABLE`。不是网络、密钥、超时、输出长度或安全过滤的问题。
- **修复**：可引用集合改为"问题检索结果 + 本报告发现已引用、且存在于已加载语料的规则"，并由新配置 `chat_max_allowed_rules`（默认 20，范围 1–50）限定上限。报告侧条目从语料重建，不复制库内存储的文本。伪造或未知 id、既不在检索也不在报告中的规则，仍然失败。安全过滤、超时、输出上限都未放宽。

## 真实证据（DeepSeek + RapidOCR + PG FORCE RLS 非 owner 角色 + 回环 Redis；ASGITransport，inline）

- **修复前**（提交 `a90e18e`，业务代码等同 `aaee76a`）：5 问中 2 问失败。
  - 失败的是 `broad_fields` 和 `broad_zh`，均为 1 个 error 事件、0 个 delta。
  - 失败阶段都是 `cites_outside_question_retrieval`，越界引用的规则 id 全部来自本报告的发现。
  - 输出安全标记全部为 false，PII 计数为 0。
  - 修复前另有一轮探索性运行（4 个宽泛问题全部失败，原因相同），其文件未保留，不作为证据。
- **修复后**（提交 `74ba6be`）：2 轮 × 5 问，10/10 成功。
  - 报告为 L0 / `llm_verified=true`。
  - 每问 HTTP 200，至少 1 个 delta，0 个 error。delta 拼接结果与 done 一致；完整回放逐事件相同。
  - 每个引用都在"检索 ∪ 报告"范围内。LLM provider 仅为 deepseek，无 fake。
  - 单问耗时最大约 4.1s。
- 证据只记录计数、规则 id、阶段和耗时，不保存模型原文、提示词、cookie、密钥或连接串。

## 回归与扫描

- 默认全量回归在活库 PG/Redis 上运行，子进程移除了云密钥和真实模型开关：**396 passed, 4 skipped**。4 项跳过都是外部模型 opt-in 测试：DeepSeek realpath、本次新增的 DeepSeek 多问题测试、Ollama、空库存探测。默认成功场景仍使用测试替身，不算真实模型证据。
- 新增替身单测 `test_chat_report_citations.py`，覆盖以下 4 个场景：
  - 允许引用报告内规则；
  - 拒绝陌生规则；
  - 不接纳伪造 id；
  - 遵守上限。
- Ruff check 和 format 通过；Bandit 对 app 无发现；gitleaks 扫描提交区间与工作树均无泄漏。用密钥值反查仓库和证据目录，命中数为 0。

## 范围外 / 未验证

- 不是浏览器、生产包或 ARQ worker 的端到端测试；样本量小，不是 P95 或稳定性认证。
- 检索仍是轻量回退方案，不是 BGE。语料混有合成规则，不代表实际法律合规。
- 本地 Ollama 推理仍未验证。

## 复现

`RUN_DEEPSEEK_E2E=1 DEEPSEEK_SSE_ROUNDS=2 pytest tests/test_deepseek_chat_diagnosis.py`

密钥只能从私有 env 注入子进程，并且要设置 `DEEPSEEK_EVIDENCE_DIR`。加 `DEEPSEEK_SSE_DIAGNOSE_ONLY=1` 时只诊断、不做断言。
