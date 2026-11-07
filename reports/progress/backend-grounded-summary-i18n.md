# ST-143：grounded summary 自然句模板与语言一致性

分支 `feat/backend-grounded-summary-i18n`；在 c681de7 后新增提交，未改写原提交。基线 `050a4c945e1291c3fce4871ec28a151a29788f55`（匿名只读 fetch，未推送）。本次没有模型调用、余额请求、8002 健康探针或重启；不改变运行中的服务。

## 行为

- 实际 API Language 是 `zh-CN / en / ru / vi / pt / ar`，ReviewCreate 和数据库默认均为 `zh-CN`。前端使用 `zh-CN / en / vi`；实现这三种语言并保留 `ru`，共四套模板。`vi` 不再回退中文；内部别名 `zh`、未知值及尚无模板的 pt/ar 回退 `zh-CN`。API 的 Literal 校验不变：非法 language 仍拒绝，内部 fallback 不扩大 API 接受值。
- `review.process_review` 显式传入 `row.language`；仅满足原有重建条件时生成自然句，不改变原有规则/关键词触发策略；不相关模型摘要仍逐字保留，不自动翻译。
- 只读取 retained finding 的 severity 和 citation rule IDs，生成问题数、高风险数、关联规则和已过滤数，以及人工复核建议；不接触文档值、不调用模型。
- N 按 finding 对象计数，不是 unique rule 数：**severity=info 且只引用 SYN-REVIEW 的纯范围说明不计作问题**。混合引用、非 info 的 finding 不被整体排除；info finding 中的 SYN-REVIEW 不进入规则清单。其他 info finding 仍计数。
- X=0 时省略高风险分句；没有问题时采用仅描述 retained findings 的零问题句，不声称清关或法律结论。
- 规则去重、排序，只列前5项；中文顿号/“等”，英文 and/Oxford comma/“etc.”，俄文 и/“и др.”，越南文逗号 + và /“v.v.”，句末不产生重复句点。
- 英文 issue/conclusion 单复数；俄文问题、无依据结论及动词按 1/21、2–4/22–24、5–20/25 等分组变化，覆盖11–14、111–112等例外。
- `model_output_filter` 的逻辑/计数不变；现有 corpus scope/disclaimer 前缀原样保留（包括原本的中文文本），本次仅本地化重建正文。没有顺带本地化原有降级提示。
- opt-in capture 的摘要 wrapper 仅同步新 language 参数，不执行付费测试、不改历史 ledger。

## 示例（纯合成计数；2个问题、高风险1、过滤2，info SYN-REVIEW 已排除）

### zh-CN

保留的审查结果共列出 2 项问题，其中高风险 1 项，涉及规则 SYN-AMOUNT、SYN-HS。已过滤 2 条无依据结论，建议人工复核。

### en

The retained findings identify 2 issues, including 1 high-risk issue. They cite rules SYN-AMOUNT and SYN-HS. Removed 2 unsupported conclusions. Manual review is recommended.

### ru

В сохранённых результатах проверки отмечены 2 проблемы. Из них 1 проблема с высоким риском. Выводы связаны с правилами SYN-AMOUNT и SYN-HS. Отфильтрованы 2 необоснованных вывода. Рекомендуется проверка специалистом.

### vi

Các kết quả được giữ lại nêu 2 vấn đề, trong đó có 1 vấn đề rủi ro cao, liên quan đến các quy tắc SYN-AMOUNT và SYN-HS. Đã lọc 2 kết luận không có căn cứ, khuyến nghị xem xét thủ công.

越南文不屈折变复数，保留重音符；零问题句仅描述 retained findings，X=0 时不写高风险分句。

## 验证与复现

离线/fixture 验证，不构成真实模型证据。新增各语言自然句、零 findings/只有范围说明、英文单复数、俄文1/2/4/5/11/12/14/21/22/25/111/112、一条规则多问题、rule cap/分隔符、未知语言 fallback、输入/计数不变、保留不相关摘要测试。mock API 测试覆盖四语言从 row.language 到摘要，并断言 scope/disclaimer 前缀及 filter flags 保留。

```sh
# public read-only, no credential helper/header, no push
# 已执行一次，基线完整 hash 如上
git -c credential.helper= -c core.askPass= -c http.extraHeader= -c credential.interactive=never fetch --no-tags https://github.com/RosenFFF/- main
git worktree add /workspace/competition/worktrees/backend-grounded-summary-i18n -b feat/backend-grounded-summary-i18n 050a4c9

# cwd: backend；wrapper 仅注入指定私有 PG/Redis child env，清空 RUN_* 和云模型 key
python3 /workspace/competition/backend-grounded-summary-i18n-evidence/run_regression_private.py tests/test_grounded_summary_i18n.py tests/test_review_summary_prompt.py tests/test_model_fp_offline.py
python3 /workspace/competition/backend-grounded-summary-i18n-evidence/run_regression_private.py

# cwd: repository root；ruff 来自既有 71311f4 backend venv
ruff check backend
bandit -r backend/app backend/eval -q -f json -o /workspace/competition/backend-grounded-summary-i18n-evidence/bandit.json
gitleaks dir . --redact --no-banner --report-format json --report-path /workspace/competition/backend-grounded-summary-i18n-evidence/gitleaks-worktree.json
python3 /workspace/competition/backend-grounded-summary-i18n-evidence/verify_key_absent.py
# 最终提交后，回执外置避免 hash 自引用
gitleaks git . --redact --no-banner --log-opts='050a4c9..HEAD' --report-format json --report-path /workspace/competition/backend-grounded-summary-i18n-evidence/gitleaks-range.json
```

原 c681de7 验证：定向66、全量472 passed / 7 skipped。本次越南文定向：73 passed，2.32s；本次全量真实 PG/Redis 注入回归 **479 passed，7 skipped，113.59s**（付费 opt-in 全部跳过）。Ruff通过；Bandit app+eval 0 findings，Gitleaks工作树 0 findings，真实key字节比较 0 hits；最终提交范围扫描回执外置。
扫描只报告结果数；key 比较在进程内执行，只打印 hit count。私有配置/key/实际账户余额不写入任何交付文件。最终 bundle 为 `/workspace/competition/bundles/feat-backend-grounded-summary-i18n.bundle`，范围 `050a4c9..tip`，最终 hash/verify 回执外置。

便携证据：`reports/evidence/backend-grounded-summary-i18n/`；外部原始回执：`/workspace/competition/backend-grounded-summary-i18n-evidence/`，均带 README 与 SHA256SUMS。
