# 前端 M3 polish — feat/frontend-m3-polish

基线：`d499513`。对比度跟进提交在 tip。

## 范围
- set-state-in-effect 修复（AuditPage / DemoAuditPanel / RateLimitNotice + `useClock`）
- FlowTrail / skip-link / upload·ask 空态；验单台 tokens
- axe color-contrast：取消对 `elmPartiallyObscuring` 的软放行；未决项须无遮挡复测（isolate）+ 记录 WCAG AA 手动比值

## 对比度要素（mock e2e）
| 视口 | 元素 | 场景 | fg / bg | 比值 | AA 4.5:1 | axe |
|---|---|---|---|---|---|---|
| 390 | `.source-disclaimer`（ask） | 曾 incomplete | ink `#1a1c1e` / canvas `#eef0f3` | **14.97:1** | PASS | 布局修复后 **无 incomplete** |
| 1440 | `.citation-body`（report-missing-source） | incomplete elmPartiallyObscuring（与 shell 叠层） | ink / canvas | **14.97:1** | PASS | 页面 axe 仍 incomplete；**isolate 复测 axe=pass** + 比值已写入 sidecar |

证据：`/workspace/competition/screenshots/m3/contrast-verification-{390,1440}.json`

## 检查
- oxlint `--deny-warnings` / tsc / vitest 94 / build + prod-no-mock/demo / mock e2e 390·1440：pass
- security：本分支 range + worktree C/H=0；整仓历史 C=6 属后端分支 `077b21d`（见 `reports/security/2026-11-06-frontend-m3-scope.md`）
- 未碰 real-backend fixture / tenant gate
