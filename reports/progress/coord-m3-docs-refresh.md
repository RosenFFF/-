# M3 提交材料事实刷新（匿名）

- 分支 `feat/coord-m3-docs`，独立工作树 `/workspace/competition/st143-m3`。
- 原 tip `76854ab` 的两项本地提交已重放至 main `aaee76a`。冲突位于 `PLAN.md` 与 `reports/progress/2026-11-07-0906.md`，保留主线版本，避免旧进度覆盖新事实。没有合并或推送主线。
- 四份 submission 文档更新为 v0.4，分别区分真实模型 ASGI、前端 L3 开发环境和本机服务恢复证据；删除过时的未获密钥/llm_verified=false 总结及 BGE 已部署暗示，保留失败路径和所有未测项。
- 原始证据、私有配置和历史归档未修改；没有读取密钥文件。证据路径见各文档的 D/F/S 索引。

## 本轮检查

- `git diff --check` 通过。
- `bash scripts/security-scan.sh` 返回 0；Semgrep、Bandit、gitleaks（历史+工作树）、Trivy、pip-audit、npm audit 全部执行，无 SKIPPED 或 ERROR。CRITICAL/HIGH/MEDIUM/LOW 均为 0。完整结果见 `reports/security/coord-m3-docs-refresh.md`（记录扫描时 HEAD 加文档工作区，不假称最终提交本身已存在于扫描时）。
- 独立 `gitleaks git . --log-opts='main..HEAD' --redact` 与 `gitleaks dir . --redact` 返回 0，无发现；外部脱敏 JSON 为 `/workspace/competition/bundles/coord-m3-docs-gitleaks-{range,tree}.json`。
- 本轮仅文档变动，未重跑业务测试、未调用付费模型。391 passed/3 skipped 等数据仅引用已有证据，不是本轮新跑结果。

## 剩余工作

宽泛追问的应用层 MODEL_UNAVAILABLE 根因和多问题真实回归；浏览器+生产包+真实模型+PG/Redis 联合验收；P95/并发/准确率/消融/成本评测；Ollama 模型安装与真实本地推理；部署重启保障与正式彩排。检索/重排仍为轻量回退，不是 BGE。
