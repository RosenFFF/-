# 安全扫描说明 — feat/frontend-m3-polish（2026-11-06）

`scripts/security-scan.sh` 对**整仓 git 历史**跑 gitleaks，会扫到其它分支的提交。

| 范围 | CRITICAL | HIGH | 说明 |
|---|---|---|---|
| 工作区 `gitleaks dir` | 0 | 0 | 当前 frontend worktree |
| `d499513..feat/frontend-m3-polish` | 0 | 0 | 本分支新增提交 |
| 整仓 `gitleaks git` | 6 | 0 | 全部来自 `feat/backend-m3-demo-env` @ `077b21d`（`reports/progress/backend-m3-demo-env/validation-summary.json`）；**不是**本分支祖先 |

本 tip 的 frontend 变更与工作区目录密钥扫描为 **CRITICAL=0 HIGH=0**。整仓历史 6 条需后端分支侧处理，不计入本次前端 polish 验收阻断。
