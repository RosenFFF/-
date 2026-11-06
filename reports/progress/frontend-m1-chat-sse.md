# 前端追问 / SSE（对接后端 40809ef，OpenAPI 0.3.3）

日期：2026-11-05（America/Tijuana）。分支 `feat/frontend-m1-api`，基线 `d3c0b09`。联调后端 `40809ef`。

## 范围

- GET `/reviews/{id}/messages` 历史
- POST JSON / SSE：`delta` → `citation` → `done` / `error`；引用复用 Provenance
- `Last-Event-ID` 续传（退避、按事件 id 去重、键盘/读屏 status）
- credentials + CSRF；`blocked=true` 安全拦截文案；503 `MODEL_UNAVAILABLE` 三语文案；不伪造成功流、不回退 mock；其它未实现路由仍映射 501

## 验收分层（勿混）

### 测试桩 / 夹具通过（非真实模型）

- Vitest：SSE 帧解析、续传去重、503、blocked、resume 404
- 真实 HTTPS 夹具联调（isolated SQLite + fakeredis + 合成账号）：无模型时 SSE `error`/`MODEL_UNAVAILABLE`；跨用户 history/replay **404**
- 浏览器真实截图 `real-ask-{390,1440}.png`（无 MOCK 红条）展示不可用提示

### 真实模型验证（仍阻塞）

- 本环境无可用 LLM / 模型下载受阻，**未**完成真实模型端到端成功流验收
- 不宣称已生成真实 LLM 追问答案

## 检查

build / oxlint / vitest / mock e2e（含 axe·overflow·keyboard）/ real e2e / npm audit 0 / security-scan CRITICAL/HIGH=0
