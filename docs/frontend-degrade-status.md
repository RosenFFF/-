# 前端交接（ST-143）

降级状态条的基线是 `905349c`，提交 `d887503`。本次过滤行叠在该提交上，没有变基，也没有改本地后端。

只读核对过 `origin/main` `c8c9a00`（合并 `73c2eb4`）。`d887503` 不在该 main 上，`DegradeStrip` 也不在 main 的树里，因此没有把 UI 当成已合并而丢弃。`docs/api.yaml` 的 `SecurityFlags` 仍未声明 `model_output_filter`；运行时形状以 `review_out` 和 `backend/tests/test_m1_pipeline.py` 为准。

## 无依据模型结论计数

审查响应把 `filter_model_findings` 的计数字典放在 `security.model_output_filter`。内部变量名叫 `flags`，落库和出参字段是 `security`，响应里没有另一个叫 `flags` 的对象。

`filter_model_findings`（`backend/app/services/model_findings.py`，`73c2eb4`）写出的键：

| 键 | 含义 | 界面 |
| --- | --- | --- |
| `unsupported_finding` | 引用的合成前提不是 `true`（假或未知）而被丢掉的模型结论条数 | 唯一展示的 N |
| `duplicate_finding` | 引用已全被确定性结论覆盖而被丢掉的重复项 | 不展示 |
| `duplicate_citations_removed` | 保留项上删掉的重复引用数 | 不展示 |

`security.invalid_citations_dropped`、`output_checks_passed`、`finding_counts` 都不是这个 N。过滤函数没加过的键不会出现；空字典表示没有计入任何一类，不等于显式 0。

只渲染有限、非负、安全整数且大于 0 的 `unsupported_finding`。显式 `0` 与 `-0` 识别为 0 并隐藏：这句话是在说明丢掉了结论，0 会读成清场。缺字段、`null`、负数、小数、字符串、非有限数、布尔、数组和其他畸形值都不显示，也不改写成 0。文案只有「已过滤 N 条无依据的模型结论」及其英越对应句，不说剩余结论已通过法律或合规验证。这一行在审查结果列表上方，不放进降级状态条，也不使用降级字段。

## 降级状态条

协调者早先告知的 main `40669a6` 已被 `c8c9a00` 取代。降级条仍然基于 `905349c`，没有吸收这两次后端提交里的其他前端差异。

## 各能力只读自己的字段

| 表面 | 读什么 | 不读什么 |
| --- | --- | --- |
| 抽取（识别结果） | `degrade_level`、`degrade_status`、`llm_verified`、本结果的 `models` 轨迹 | `/system/models`、审查、追问、字段 `source` |
| 审查报告 | 同上，来自该报告 | 系统健康、抽取、追问 |
| 追问消息 | `role`、`blocked`、`models` | 消息上没有 `degrade_level` / `degrade_status` / `llm_verified`。即使对象上多出这些字段，组件也不读取 |
| 系统健康 | `/system/models` 的 `degrade_level`、`models[]`、`llm_provider_chain` | 任何历史报告或消息 |

级别只接受精确的 `L0`、`L1`、`L2`、`L3`。空缺是「未确认」。` L0 `、`l0` 之类不改写成 L0。`llm_verified` 只接受布尔值。

来源：

- 抽取 / 审查 / 追问：本载荷里 `category=llm` 的轨迹。优先最后一条 `ok` 或 `fallback`，否则最后一条 `failed`。OCR 或其他类别不算 LLM 来源。
- 系统健康：第一条 `category=llm` 且 `healthy===true` 的条目（与后端选定方式一致）。`healthy` 不是布尔 `true` 则忽略。
- 模型名只显示轨迹或健康条目里的字符串。没有 qwen 字样就不称 qwen。

L0 文案是云端模型，L1 是备用云端模型，L3 是规则引擎并且写明须人工复核。L2 只有级别字段本身是 `L2` 时才标成 L2，并写明这不是已验收的离线能力，也不表示完整离线流程可用。本地模型名称（例如 ollama 的 `qwen2.5:7b`）可以出现在来源行，同时带「不是已验收能力」。系统健康条另有一句产品定位：云端模型为主、规则引擎为回退。这句话标明不是本页测得结果。历史抽取和报告不带这句，避免把定位说成那份记录的结论。

级别与来源冲突时两个事实都保留，不互相改写（例如 L2 配上云端轨迹，或 L3 配上 `ok` 的模型轨迹）。

无健康 LLM 的横幅只陈述 `healthy` 均为 false，不据此改写 `degrade_level`，也不改写已保存的抽取、审查或追问。

## 静态无障碍与响应式

状态条用现有 `--ink` / `--paper` / `--brand` / `--ink-secondary` / `--risk-low`。文字说明级别，左侧色条不是唯一信号。对比是用这些十六进制按 sRGB 相对亮度算的 WCAG 比值，**不是**浏览器绘制结果。抽查的正文、次要字、品牌色、风险色配对均 ≥ 4.5:1，因此没有改色。

样式上：状态条 `flex-wrap` 且段落 `white-space: normal`，避免 390 宽被一行撑破；1280 仍是同一条，不是三列卡片。导航、流程条和主按钮的样式最小高度为 44px。状态条没有 `tabIndex`，也不会 `.focus()`。页面级条是 `role="status"`、`aria-live="polite"`。追问每条消息的条是 `aria-live="off"`，避免和流式正文一起反复播报。历史列表不再整体 `aria-live`；只有当前这条回答的正文在发送期间是 polite。重连横幅原有的聚焦没有改，那不是后台状态刷新。

`prefers-reduced-motion` 下状态条 `animation` / `transition` 为 none。条本身没有入场动画。

这些检查不能证明：真实 Tab 顺序、焦点是否在刷新时被抢走、抗锯齿后的对比度、或 1280 / 390 视口里的换行。浏览器验收按下面清单在演示机做。本次没有启动浏览器、Playwright、Chromium、开发服务器或在线接口。

## 演示机仍须人工看的项目

1. 键盘从「跳到主要内容」走到上传、识别、审查、追问、模型链路，确认状态条不插入 Tab 顺序。
2. 打开模型链路并等待 `/system/models` 返回，确认焦点留在原处。审查轮询更新时同样不抢焦点。
3. 用系统对比度或开发工具复测状态条文字与纸色、导航选中态（品牌色在 `--brand-subtle` 上）、错误横幅。以绘制结果为准。
4. 在 1280 和 390 宽度看抽取、报告、追问、模型链路：状态条换行，文字不被裁切，导航可点区域不小于 44px。
5. 用一份抽取为 L3、审查为 L0（或实际返回的其他组合）、追问轨迹为另一个模型的真实响应，确认三处文案各自跟随自己的字段，且模型页的当前健康不改写那份报告。
6. 若响应里的 `degrade_level` 确为 L2，来源行应出现该条轨迹或健康条目中的模型名，并同时看到「不是已验收的离线能力」。没有 L2 字段时不得出现 L2。
7. 完成的审查若 `security.model_output_filter.unsupported_finding` 为正整数，结果列表上方只出现该数字的过滤句。显式 0、缺字段，以及只有 `duplicate_finding` 时不出现这句。这句不在降级条内，也不写剩余结论已通过验证。
