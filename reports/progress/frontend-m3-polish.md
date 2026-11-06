# 前端 M3 polish — feat/frontend-m3-polish

基线：`d499513`（main 已合并 backend `87ff58c` + frontend `b2ae74f`）。

## 范围
- 消除 AuditPage / DemoAuditPanel / RateLimitNotice 的 `set-state-in-effect`：deadline + `useClock`(useSyncExternalStore)、表单 `requestSubmit` 启动统计、无 suppress 注释。
- 流程连续性：`FlowTrail`、skip-link、上传已选文件态、追问 loading/empty、焦点/键盘与 390/1440 打磨；tokens 对齐验单台；诚实 503 MODEL_UNAVAILABLE；生产无 mock/demo 入口。
- e2e：mock visual-a11y 输出至 `screenshots/m3/`（sidecar `environment.kind=mock`）；real-audit sidecar 标明 SQLite/fakeredis + `backend_commit=87ff58c`。

## 检查（本机）
| 检查 | 结果 |
|---|---|
| oxlint `--deny-warnings` | pass |
| tsc --noEmit / tsc -b | pass |
| vitest | 7 files / 94 tests pass |
| prod build + check-prod-no-mock + check-prod-no-demo | pass |
| mock e2e 390/1440 axe | pass → screenshots/m3 |
| real-audit fixture vs 87ff58c | **gap**：serve_fixture 启动报 `verified tenant context required before SQL`（87ff58c 租户门禁）；未宣称活库验收 |
| npm audit | C/H=0 |
| security-scan.sh | CRITICAL=0 HIGH=0 |

## 诚实标签
- 真实模型：不可用时如实 503，不造假流。
- 联调库：fixture 为 SQLite + fakeredis 替身，不作 Postgres/RLS 活测声明。
