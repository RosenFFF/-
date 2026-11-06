# M1 补充：模型回退与引用来源分离

日期：2026-11-05（America/Tijuana）。基于 e7c806f，仍在 feat/frontend-m1-api；仅本地前端 worktree，不动后端、不推远程。

## 行为

- 报告顶部独立状态条：L3 明示「规则引擎回退，未完成真实 LLM 验证」，另保留 L3 技术值；zh/en/vi 均有完整文案，不只显示级别。L0/L1/L2 分别显示正常/备用云端/本地离线及人工复核提醒。若 llm_verified=false 与其他级别矛盾，保守显示未完成验证，不宣称成功。
- 报告级规则来源单独显示，仅读取 security.source_kind；security.retrieval_mode=lightweight_hash 时明确「轻量哈希检索（非 BGE）」，bge 则如实显示；compliance_disclaimer 有值即展示。
- 报告引用、展开规则及追问引用复用 CitationSource。source_kind=synthetic →「合成规则 · 非真实合规结论」；public →「公开摘要」，并明确「公开摘要，非法规原文，不代表已通过合规验证」。
- 每条显示来源 URL、条款定位 article、版本日期 version_date。四字段均可选/可空，缺失、空值或未知 kind 均显示「来源信息缺失」，不从 L3、source/summary、规则 ID、corpus 或其他日期推断/补造。
- URL 仅允许无内嵌凭据的绝对 HTTP(S)，以 noopener/noreferrer 新窗口链接呈现；拒绝 javascript/data/file/相对地址。长 URL 可换行，焦点仍可见。
- mock 显式声明 synthetic，但不伪造 URL/版本日期；浏览器额外 public/缺失场景仅在显式 mock 测试进程内改 adapter，绝不作为运行时失败回退机制。

## 契约核对与后端待办

本次只读核对 st143-backend 的 M1 工作区（不是后端运行验收）：services/provenance.py 已给 degrade_status/llm_verified 和聚合 source_kind/retrieval_mode；services/rag.py 的 citation() 已给 source_kind、url、article、version_date。前端已对接这些实际字段，不再沿用上一轮「全部来源字段尚缺」的结论。

仍需统筹/后端确认：

1. 将 M1 来源扩展的 API 契约并入主线；本前端基线 docs/api.yaml 仍是 d3c0b09 的 v0.3.0，因此兼容旧响应的字段均为 optional，未擅自覆盖另一工作区契约。
2. GET /rules/{rule_id} 当前直接返回原始规则记录，尚未统一构造 source_kind/version_date；应与引用接口返回一致的明确元数据。前端在规则详情中如实显示缺项，不拿引用类型或旧日期硬补。
3. GET /reviews/{id} findings[].citations、历史及 SSE citation 应持续携带各条 source_kind/url/article/version_date；旧记录/空值仍需补充真实元数据。合成规则若本无真实公开 URL/日期，应保留缺失提示，而不是伪造链接或时效。
4. source_kind=public 仅标识公开摘要来源，不是本票合规结论或真实 LLM 验证完成；报告 L3 可以与 public 引用同时出现。

未新增真实 LLM key 或真实后端浏览器联调。实际服务响应、历史数据兼容及真实交易适用性仍需后端合并后验收。

## 回归证据

- 新增 Vitest：三语准确文案，L3+public 不误标 synthetic，缺失不推断，字段完整/空值，其他日期不冒充 version_date，检索标识，安全 URL。
- 保留此前 HTTP501 三语和绝不回退 mock 的全部测试。
- 浏览器每个视口新增 report-public / report-missing-source；仍覆盖原 9 状态，检查实际字段显示、警告及互不混淆。
- 新版首跑捕获一个 ARIA 问题：为无角色 div 添加 aria-label。已改成具名 section；未排除/禁用 axe 规则。
- 最终 build 通过；oxlint 0 警告/错误；Vitest 73 项（4 文件）通过；严格 e2e TypeScript 检查与 2 个完整旅程通过。
- 22 组页面/状态水平溢出、超宽元素均为 0；axe 默认全页规则 violations/incomplete 均为 0，无排除或禁用。
- 314 个实际 Tab 停靠点通过顺序、焦点、视口及无遮挡检查；最低焦点环对比度 6.76:1；原有 14 项键盘操作全部通过。页面 JS 错误、真实 API 请求均为 0。
- npm audit 0 漏洞；根 security-scan 六工具全部运行，CRITICAL/HIGH/MEDIUM/LOW 均为 0；另跑工作区 gitleaks dir，0 泄漏。安全报告中的 e7c806f 是扫描时 HEAD，代码扫描包含本次工作区。
- 机读结果已更新到 frontend-m1-browser-summary.json；24 张最终 PNG 的顶部 mock 红条全部经像素复核。

截图目录 /workspace/competition/screenshots/m1/，每个名字均有 -390.png 和 -1440.png：login、cases、upload、extract、report、report-public、report-missing-source、ask、audit-reviewer-403、audit-admin、models、keyboard-field-focus（附加焦点证据）。共 24 张；是有红条的 mock 视觉验收，不是真实报告证明。
