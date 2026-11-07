# 演示机验收步骤

## 边界与前提

本机浏览器验收状态为 **平台策略限制，不可在本机执行**。托管策略 `LoopbackNetworkBlockedForUrls: ["*"]` 不得绕过：不改策略、不换内网地址、不建隧道、不借代理规避。此前平台上的 Shell Playwright 探测不计入验收证据。以下只在获准的独立演示机执行；如果演示机也有同类策略，停止并记录限制。

本提交仅交付脚本和静态/单元检查结果，**尚无演示机浏览器实测**。运行后才能将其产物标为“Playwright 无头 Chromium 实测”，不能标为桌面浏览器。Vite preview 承载的是生产 `dist/`，不等于正式部署。

演示机需要 Node/npm、Python 3、已安装的 Playwright Chromium，以及受演示机浏览器和 Node 信任的本地 HTTPS 证书。按机器管理规范建立信任；禁止 `ignoreHTTPSErrors`、关闭 TLS 验证或浏览器安全。前端使用回环 HTTPS，后端必须由负责人先确认真实 PG / Redis、租户隔离与启动门禁启用、模型健康 L0；保留独立环境证明，不用本脚本的 UI 结果反推数据库或检索模型。不能用 SQLite/fakeredis 或旧 fixture 替代。不得启动本地模型下载。

使用专用合成验收账号和不含个人/商业秘密的合成 PDF；账号具备上传、审查、追问权限。不要把密码或模型密钥写进命令历史、文档、日志或证据。浏览器根本不需要模型密钥。

## 准备与执行（演示机的仓库 web/）

先审核并应用本次 bundle；记录实际前后端提交。安装依赖和 Chromium（若已安装则无需重复安装）。运行：

```bash
npm ci
npx playwright install chromium
npm run lint
npm test
npm run build
npx tsc -p tsconfig.e2e.json
python3 scripts/test-demo-trace.py
```

通过进程环境传入以下值；这些命令仅用于演示机，不在平台电脑执行。地址是本机示例，必须对应演示机上实际运行的服务：

```bash
export ST143_DEMO_MACHINE=1
export ST143_DEMO_FRONTEND_URL=https://127.0.0.1:5175
export ST143_DEMO_BACKEND_URL=http://127.0.0.1:8002
export ST143_DEMO_FRONTEND_COMMIT="$(git rev-parse HEAD)"
# 填入已核实的后端完整提交，不填猜测值。
export ST143_DEMO_BACKEND_COMMIT=REPLACE_WITH_VERIFIED_BACKEND_COMMIT
export ST143_DEMO_SAMPLE_PDF=/absolute/path/to/synthetic-invoice.pdf
export VITE_USE_MOCK=false
# 每次生成新目录，不能复用/覆盖历史证据。
export ST143_DEMO_RUN_DIR="$(mktemp -d /tmp/st143-demo-XXXXXXXX)"
# bash 交互读取，不在命令历史里留下账号值；关闭 shell 调试输出。
set +x
read -r -p '合成验收用户名: ' ST143_DEMO_USERNAME
read -r -s -p '合成验收密码: ' ST143_DEMO_PASSWORD
printf '\n'
export ST143_DEMO_USERNAME ST143_DEMO_PASSWORD
npm run test:demo-machine
unset ST143_DEMO_USERNAME ST143_DEMO_PASSWORD
```

不得把实际密码发到群里。配置自动启动新的 HTTPS Vite preview，将 `/api` 代理到 `ST143_DEMO_BACKEND_URL`（内部设置 `ST143_API_PROXY_TARGET`）；端口被占用即失败，不复用不明服务。前后端环境变量都只接受回环 HTTP(S) origin，前端额外要求 HTTPS。普通 dev / preview 可直接用 `ST143_API_PROXY_TARGET` 配置，详见 web/README.md。

脚本不启动、重启、迁移或降级后端，不做账号种子，不使用 mock 路由或存储态文件。只运行一个 Chromium 桌面尺寸视口、一个 worker、零重试。每次正常验收会创建一份单证、一份报告和三轮模型追问；模型调用还可能包括报告生成。失败后先检查证据，不自动重跑，以控制费用；不做准确率或 P95 批量评测。

## 流程和通过条件

1. 打开登录页，留空表单截图；登录后再开始录制 trace，避免录入凭据进入 trace。
2. 上传合成 PDF，进入识别页，留上传及识别结果截图。
3. 点击发起审查，等待结论；检查对应真实 API 报告为 `completed`、非空摘要、`degrade_level=L0`、`llm_verified=true`。这是浏览器流程后的附加数据断言，不以 API 结果替代浏览器。
4. 三轮追问依次为金额差异处理、**全面分析主要合规风险和修改建议**（宽泛问题）、按本报告引用条款确定修改优先级。每轮等待 UI 完成、留截图，检查真实 POST 返回 SSE、HTTP 200、非空且未阻断的 assistant `done`、最终事件 `done`，无 `error`/非法 JSON。不能只看 HTTP 200，不能把部分流或规则回退判成真实模型成功。
5. 三轮均显示新增的非空 assistant 消息，无错误提示；console error、pageerror、requestfailed、HTTP 4xx/5xx 计数均为零。任一步失败即整轮失败；宽泛问题失败必须如实报告，不称整体稳定。

可能发生的真实失败：证书未受信任、平台策略拦截、端口占用、登录/权限失败、OCR 超时、L3、SSE error 或提前中断。脚本不会替换模型、绕过策略、放宽鉴权或重发请求。先保存失败证据，再由负责人决定下一轮。

## 证据与脱敏

`$ST143_DEMO_RUN_DIR/evidence/` 包含：

- `01-login-empty.png` 至 `08-follow-up-3.png`：逐步截图；失败时已登录才尝试 `99-failed-stage.png`。仅允许合成材料，截图不保证自动文本脱敏。
- `summary.json`：实际环境地址/提交、阶段、整体通过与否、三轮 SSE 事件摘要和耗时、四类错误计数。只有运行过才存在，不预填成功结果。记录时间带 UTC 偏移/时区含义，汇报时换算 America/Tijuana。
- `network-sanitized.har`：**仅网络元数据**，由安全白名单构造；无 Cookie、认证请求体、任何请求/响应体、请求/响应头和 URL 查询/片段。不是可回放 HAR，time/timings 是 HAR 结构占位，不用于性能结论。
- `trace-sanitized.zip`：登录之后的视觉帧和最少动作元数据。移除所有 network、DOM 快照、源码、动作参数、结果、日志及原始错误；仅保留截图资源。不是完整网络调试 trace，离线查看能力须在演示机确认，本机未验证 viewer。

trace 只在私有临时目录短暂写原始包，随后标准库脚本白名单脱敏并删除临时目录；脱敏失败时不发布原始包，`summary.json` 标为未通过。普通 Playwright 自动 trace/录像/失败截图关闭，避免另存未脱敏材料。只能提交上述脱敏证据，不提交 `runner/` 原始诊断、账号环境变量、临时目录或密钥。发布前人工复查所有图片和文件内容；未完成复查不能声称完全脱敏。

首轮结果与源码交付分开报告：分支/提交、演示机实际前后端版本、入口、执行模式、测试退出码、失败阶段、错误计数、三轮 SSE 结果、证据目录和归档校验值。当前检索仍需按实际轻量回退标注，不得写成 BGE；Ollama 探测失败统一写“本轮 Ollama 可达性探测失败，模型库存未知”。
