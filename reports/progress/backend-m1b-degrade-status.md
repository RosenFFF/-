# backend M1b degrade_status + citation provenance

- 契约补齐：报告/识别返回固定 `degrade_status`、`llm_verified`；L3 文案恒为「规则引擎回退，未完成真实 LLM 验证」。
- 每条引用固定 `source_kind`/`source_kind_label`/`url`/`article`/`version_date`（优先 verified_at），并标 `excerpt_kind=summary`、`applicability=unverified`（公开摘要≠法规原文/完整适用证据）。
- Ollama 权重下载仍受网络限制（redirect/198.18.0.1），如实记录，未绕过；当前仍为规则引擎回退，未完成真实 LLM 验证。
- 测试：108 passed, 1 skipped；security-scan CRITICAL/HIGH=0。
