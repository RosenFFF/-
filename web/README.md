# 丝路智审 · 前端

React + TypeScript + Vite。接口：`../docs/api.yaml` v0.3.0；视觉：`../docs/design.md`「验单台」。

## 运行与安全

```bash
cd web
npm ci
npm run dev -- --port 5173 --strictPort
```

打开 **https://localhost:5173**，仅开发时信任本机自签证书。`@vitejs/plugin-basic-ssl` 的证书/私钥保存在被忽略的 `node_modules/.vite/`，不入库。生产环境使用正式证书与 HTTPS 反向代理，不使用开发证书。

Vite `/api` 代理到 `http://127.0.0.1:8000`，不改写 Host / Origin，传递 HTTPS 的 `X-Forwarded-Proto`。浏览器只访问同源 HTTPS，服务端 `Secure; HttpOnly; SameSite=Strict` Cookie 不变。**不要关闭 Secure、放宽生产 CSRF/CORS 来联调。**

### 真实 / mock

- 默认真实接口。仅开发可 `VITE_USE_MOCK=true npm run dev`，顶部始终显示红色 **「MOCK 数据 · 仅开发」**（含登录页）。
- 生产构建无论变量为何值都禁用 mock、剔除 mock 数据，不能拿 mock 当真实处理演示。
- 故障绝不自动切 mock。未实现接口显示三语 `code` 错误及请求编号；`fields=[]` 时明确提示尚未返回字段，OCR 块不能冒充字段抽取。
- `src/api/types.ts` 为真实/mock 共用接口，`src/api/index.ts` 为唯一切换入口。

### 鉴权与主流程

- 登录只读取 `{ expires_in, user }`；真实模式通过 `/auth/me` 恢复会话，不持久化资料/令牌。启动即删除旧 `sessionStorage.sr_session`。mock 仅保存非敏感用户/角色。
- fetch 一律 `credentials: 'include'`；POST/PUT/PATCH/DELETE 从可读 `csrf_token` Cookie 取 `X-CSRF-Token`（登录例外）。不设置 Authorization，不读取访问/刷新令牌。
- 并行 401 合并为一次刷新后重试；刷新仍 401 则退出会话。重试读取轮换后的 CSRF。网络失败不重发写操作。
- 上传真实文件及 `doc_type` multipart；202 后每秒查状态，最多 180 次，可停止等待（后台仍继续）。从列表可恢复查看。
- 识别页从受鉴权端点 fetch 原件 Blob，离页/翻页撤销 URL；`locations` 按 `[x0,y0,x1,y1]` 归一化高亮，可跨页，缺失时使用 `source_block_ids` 找 OCR 块。
- 审查由用户显式发起，中文回答语言为 `zh-CN`；随后轮询。刷新报告/切语言只 GET，不重复 POST 创建。
- 条款点击 GET `/rules/{id}`；风险字段/证据链接回真实原件定位。
- SSE 处理分片 UTF-8/CRLF；断线后最多 3 次指数退避 GET 历史恢复。契约无游标/幂等键，**不重发 POST**，不能保证恢复未持久化的流。失败明确提示重新查看。
- zh/en/vi 覆盖所有契约及网络/超时/流中断码；不显示服务器原始 HTML、detail 或堆栈。

## 校验

```bash
npm run build
npm run lint
npm test
npm audit
cd ..
bash scripts/security-scan.sh .
```

Vitest 覆盖 CSRF/credentials/multipart、合并刷新/轮换、不重放网络失败、三语错误、轮询失败/超时/取消、SSE 分片与提前 EOF。

## 隔离 HTTP 联调（无 Docker、只用合成测试账号）

```bash
# 仓库根，终端 1；venv 放仓库外，避免扫描第三方源码
cd backend
UV_PROJECT_ENVIRONMENT=/tmp/silkroad-m1-venv uv sync --frozen
cd ..
M1_INTEGRATION_DIR=/tmp/silkroad-m1-integration PYTHONPATH=backend \
 /tmp/silkroad-m1-venv/bin/python -m uvicorn integration_fixture:app \
 --app-dir web/scripts --host 127.0.0.1 --port 8000

# 终端 2（web/）
npm run dev -- --port 5173 --strictPort

# 终端 3（仓库根）
M1_INTEGRATION_DIR=/tmp/silkroad-m1-integration PYTHONPATH=backend \
 /tmp/silkroad-m1-venv/bin/python web/scripts/integration-http.py
```

fixture 加载真实 FastAPI/RapidOCR，仅 SQLite/fakeredis 替换基础设施；不替换 OCR、鉴权、CSRF 或加密。密钥随机写入仓库外 `.env`（0600），保持 Secure=true、DEMO_MODE=false，不读取既有密钥、不需要 LLM key。**合成账号/该 fixture 不可用于部署。**

HTTP 脚本固定连接本机 HTTPS，显式信任本地证书（不全局禁用 TLS 校验），检查代理 Origin/Host/Proto、Cookie、CSRF、真实多页 OCR/页图、刷新/登出及缺失端点。它不是浏览器视觉验收；后端 M1 到位后需更新缺失端点预期，并补字段/报告/问答浏览器联调。

## 浏览器视觉 / 可访问性补验收

```bash
cd web
npm ci
npx playwright install chromium
npm run test:e2e
```

脚本 `e2e/visual-a11y.spec.ts` 和 `playwright.config.ts` 入库，依赖锁定于 package-lock.json。命令先严格类型检查，再自动启动 **VITE_USE_MOCK=true 的本机 HTTPS dev server**（端口 5173 必须空闲，不复用不明服务），测试后自动停止。不连接真实后端，断言无 `/api/v1` 请求且每页有 mock 红条。

两个 Chromium 视口：390×844、1440×900。分别覆盖登录、案件、上传、字段高亮、展开条款报告、追问回答、reviewer 403、admin 空审计/链校验、模型页。默认在仓库外 `../../screenshots/m1/` 保存 18 张全页 PNG、2 张键盘焦点证据图、逐页检查 JSON（完整 violations/incomplete，passes 计数） 和两个 summary JSON；可用 `M1_SCREENSHOT_DIR=/path` 指定输出目录。

每页检查 document/body 水平溢出与超宽元素列表，axe 全页默认规则（无排除/禁用项），全部可用控件的实际 Tab 顺序、`:focus-visible`、2px 焦点环、相邻色对比 ≥3:1、可见且不被遮挡。用真实键盘事件检查登录 Enter、字段 Enter/Space 切换高亮/页码、翻页 Enter/Space、追问 Enter。保留 axe incomplete，不能把待人工确认项算成通过。

HTTP 501 始终显示 `功能暂未实现` / `Not implemented yet` / `Tính năng chưa được triển khai`（即便旧后端 code=MODEL_UNAVAILABLE），另可附请求编号。真实模式错误不触发 mock；Vitest 覆盖 HTTP 错误、网络故障、生产禁止 mock。

这只是明确标注的 mock 视觉/自动可访问性验收，不是现实法律依据、真实 LLM 调用或生产合规能力证明。现有 Review/RuleCitation/Rule 契约没有机器可读的「合成规则库/轻量检索」来源标识，前端不从 summary/source 文案猜测；需要后端提供相应字段后，才能依据响应在报告与引用旁显示「合成规则 · 非真实合规结论」。
