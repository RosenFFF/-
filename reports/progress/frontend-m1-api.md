# 前端 M1 API 交付记录

基线 `d3c0b09652aa6825c43c8e9e8070c954a4a3339b`，分支 `feat/frontend-m1-api`。仅修改 `st143-frontend`，不动主 worktree、不推远程。

后续视觉及来源标注补充见 frontend-m1-visual-a11y.md、frontend-m1-provenance.md；以下测试数量为首轮记录。

## 范围与测试

- v0.3.0 同源 client/共享 wire types；Cookie/CSRF/合并刷新、无浏览器 token 存储；三语错误及请求编号。
- 真实文件上传/202 轮询、多页原件及 OCR/字段 bbox；接好字段更正、报告轮询、条款原文和证据定位。
- 追问 SSE 分片解析、断线只读历史恢复，不重放 POST。
- mock 显式开发开关/红条、生产强制禁用；真实失败不回退 mock。
- HTTPS dev/proxy 保持 Origin/Host、Forwarded-Proto=https；未改后端生产安全配置。
- 保留 package-lock.json/backend uv.lock；补可复现隔离 HTTP 联调 harness。
- npm ci/build、oxlint（0 警告/错误）、Vitest 22 项（2 文件）通过；npm audit 0 漏洞。
- 后端 pytest 42 项通过（真实 RapidOCR）。
- `VITE_USE_MOCK=true` 生产构建剔除 mock 数据、横条与 mock 存储代码。
- 根 `security-scan.sh .` 结果见同日安全报告；另补 `gitleaks dir . --redact` 工作树检查，0 泄漏。

## 真实 HTTP 联调（不是浏览器 E2E）

实际仓库 FastAPI + RapidOCR；仅基础设施替换为隔离 SQLite/fakeredis。

| 检查 | 实测 |
|---|---|
| HTTPS Vite 代理健康检查 | 200 |
| Origin / Host / Forwarded-Proto | https://localhost:5173 / localhost:5173 / https |
| 登录 | 200，JSON 无 token；2 HttpOnly；3 Cookie 均 Secure+SameSite=Strict |
| me / 缺 CSRF 写操作 | 200 / 403 CSRF_FAILED |
| multipart 两页 PDF 上传 | 202 |
| 轮询 | ready，2 页，100% |
| recognition | 200，真实 OCR，6 个归一化文本块，覆盖两页 |
| 两页页图 | 200 PNG，Cache-Control=no-store |
| reviewer 全局审计 / models | 403 / 200（后端实际健康状态） |
| refresh / logout / 再查 me | 200 / 204 / 401，刷新后重读 CSRF |

## 阻塞点与未验收项

1. `GET /documents/{id}/recognition` 当前固定 `fields=[]`（backend/app/api/v1/documents.py）。页面明示尚未返回字段，只呈现真实 OCR，不能当 LLM 抽取验收。
2. `PATCH /documents/{id}/fields`、`POST /reviews` 实测 404。基线 main.py 未注册 reviews/chat/rules；`GET /reviews/{id}`、消息/SSE、`GET /rules/{id}`、`/reviews/{id}/audit` 仍待后端。前端按契约接好，真实字段编辑/报告/条款/问答未完成验收。
3. 未读取任何真实 LLM key；基线也无对应实现，不宣称已生成真实 LLM 报告。
4. 基线 cookies.py 仍为双提交 CSRF，没有统筹补充的会话绑定/Origin 校验。未改后端；代理已实测保留正确 Origin，需后端硬化版到位后复测恶意 Origin/会话绑定。
5. SSE 契约缺恢复游标/幂等键，只能恢复已保存历史，不能保证恢复未持久化的流；三次失败明确报错，不自动重复提问。
6. 首轮未生成截图。后续已按统筹要求安装 headless Chromium，完成 mock 浏览器截图与可访问性补验收，见 frontend-m1-visual-a11y.md；真实后端浏览器流程和真机仍未验收。
7. 扫描通过不替代最终安全验收，不代表尚缺后端能力已实现。
