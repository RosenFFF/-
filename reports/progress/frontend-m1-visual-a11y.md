# M1 前端视觉与可访问性补验收

基于 `7ce7ba1`，分支 `feat/frontend-m1-api`。仅在前端 worktree 修改，不改后端、不推远程。补验收日期：2026-11-05（America/Tijuana）。

## 环境 / 重跑

- Playwright 1.65.0 + headless Chromium 158.0.8127.18；axe-core 4.13.0。
- 390×844、1440×900；zh-CN，America/Tijuana，reduced-motion。
- `cd web && npm ci && npx playwright install chromium && npm run test:e2e`。
- 严格检查 e2e TypeScript 后自动启动/停止 HTTPS Vite，显式 VITE_USE_MOCK=true；每页红条，断言 0 次真实 API 请求。
- `web/e2e/visual-a11y.spec.ts` / `web/playwright.config.ts` 入库；浏览器二进制、证书、临时 trace 均不入库。

## 发现与修复

| Before（实测） | After | Why |
|---|---|---|
| 390 上传页 scrollWidth=414，7 个超宽元素 | grid/form min-width 约束、原生文件控件 width:100%；scrollWidth=390 | 修布局根因，不用 overflow-x:hidden 掩盖 |
| 输入框/select 的 outline:none 覆盖 focus-visible；18 次焦点失败 | 统一 2px 青绿墨焦点环；全控件测试无失败 | 焦点必须可见、对比足够 |
| 登录页缺 main/H1；案件表操作表头为空 | 语义 main/H1、三语「操作」表头 | axe landmark/heading/empty-header 违规清零 |
| 空模型记录/审计仍渲染空表，引出 th-has-data-cells incomplete | 显式空状态，不渲染只有表头的表格 | 不把待人工确认项伪装成通过 |
| 选中字段/风险项无可访问的状态信息 | aria-pressed；字段 aria-controls；页码 live status | 不只靠底色表达选中/翻页 |
| 固定高度 root 会让 mock sticky 红条在深滚动后离开视口 | 自增高 app-frame，持续顶部红条；Tab 滚动后断言仍在视口 | 不能在滚动后隐瞒 mock |
| 侧栏语言按钮断成多行单字；移动侧栏被拉出过大空白 | 语言按钮整词换行；移动行轨 max-content | 延用验单台 token，保持紧凑而不改主题 |

## 最终结果

- 9 页面/状态 × 2 视口 = 18 组：login、cases、upload、extract（HS 字段选中高亮）、report（条款已展开）、ask（回答完成）、audit-reviewer-403、audit-admin（空状态+链校验）、models。
- 文档/body 水平溢出 0；超宽元素 0（不是仅做裁切）。
- axe 全页默认规则，无排除或禁用：18 组 violations=0、incomplete=0。
- 228 个 Tab 停靠点：顺序与 DOM 可用控件一致、全部可达；focus-visible/≥2px 环/≥3:1 相邻对比/视口内/无遮挡全部通过。实测最低焦点环对比 6.76:1。
- 两种视口均通过 reviewer/admin 登录 Enter、字段 Enter 高亮、Space 切字段并翻页、上页 Enter、下页 Space、追问 Enter，共 14 项操作断言。
- 页面 JS 错误 0；真实 API 请求 0。
- 截图是对应视口的全页捕获；18 张页面图 + 2 张键盘焦点证据。目录 `/workspace/competition/screenshots/m1/`；每页完整 violations/incomplete、溢出列表和 Tab/焦点数据在同名 JSON，汇总在 summary-390.json / summary-1440.json。首轮问题保存在 baseline-findings.json。

## 501 / mock 防线

- HTTP 501 优先映射 NOT_IMPLEMENTED，即便旧后端返回 MODEL_UNAVAILABLE。
- 精确文案：中文「功能暂未实现」；英文「Not implemented yet」；越南语「Tính năng chưa được triển khai」。可额外附请求编号，不显示旧的模型不可用文案。
- Vitest 覆盖三语精确文案；400/401/403/404/409/422/429/500/501/503、网络错误均不加载 mock；特别检查历史、二次翻译、追问/SSE 501 不产生 mock 返回/事件；生产即便显式 true 也不启用 mock。

## 仍需后端提供的契约字段（阻塞真实报告的来源标注）

检查当前 v0.3.0，以及后端 M1 的 review_out/条款响应后，未见机器可读的「合成规则库/非 BGE 轻量检索」来源标识。summary 的合成规则提示是自由文本，aigc 只代表 AI 内容标识，均不能冒充规则来源的稳定字段。

需后端在 Review、RuleCitation、Rule 中明确规则语料性质及版本/来源；建议统一 `rule_corpus.kind`（synthetic/legal/unknown）和 corpus id/version，并为检索链返回实际 implementation/model（字段名须由双方更新契约确认，当前前端没有擅自增加 wire 字段）。收到明确 synthetic 标识后，报告和引用旁应显著显示「合成规则 · 非真实合规结论」。当前只呈现服务器已有 summary/source/model，不用关键词猜测，不硬编码全部报告都是合成。该来源标注仍属契约待办，不能以真实法规结论验收。

## 验证 / 边界

- build：通过；oxlint：0 警告/错误；Vitest：41 项通过（3 文件）；npm audit：0 漏洞。
- e2e：严格 TypeScript 检查通过，两个完整旅程通过。
- 根 `bash scripts/security-scan.sh .`：六工具全部运行，CRITICAL/HIGH/MEDIUM/LOW=0；报告见同日安全报告。报告里的 7ce7ba1 是扫描时 HEAD，代码扫描包含本次工作区；另跑 `gitleaks dir . --redact --no-banner`，工作区密钥发现 0。
- 本轮是明确 mock 的视觉/自动可访问性验收，不是新增真实后端/LLM 联调，也不证明法律合规能力。仍需真实后端浏览器 E2E、实体移动设备和屏幕阅读器人工验收。

## 截图清单

根目录 `/workspace/competition/screenshots/m1/`，以下每个名字均有 `-390.png` 和 `-1440.png`：

- login
- cases
- upload
- extract
- report
- ask
- audit-reviewer-403
- audit-admin
- models
- keyboard-field-focus（附加键盘焦点证据）

18 组精简机读结果已入库：`reports/progress/frontend-m1-browser-summary.json`；详尽 JSON 与截图留在上述仓库外目录。
