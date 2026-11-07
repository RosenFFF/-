# 前端 Vite 可配置代理交付

- 基线：71311f416516b359c7f73cde816a8be9c5b247c3。
- 范围：Vite dev / preview 共享 `/api` 代理；配置通过进程环境变量 `ST143_API_PROXY_TARGET` 传入。默认兼容 8000，可显式指向 8002；不改变生产 JS 产物。
- 安全：只允许 HTTP(S) 回环 origin，拒绝外部地址和内嵌凭据/路径/查询/片段；报错不回显输入。HTTPS、Host / Origin、转发头和 TLS 验证设置不放宽。未读取任何密钥文件，未启动或停止后端。
- 示例（web/）：`ST143_API_PROXY_TARGET=http://127.0.0.1:8002 npm run preview -- --port 5175 --strictPort`。先完成 `npm run build`；preview 使用 dist，不是正式生产部署。

## 校验

- oxlint 通过。
- Vitest 9 文件、114 测试通过（新增配置测试 16 项）。
- `tsc -b`、Vite build、prod-no-mock / prod-no-demo 全部通过。
- `tsc -p tsconfig.e2e.json` 通过（仅类型检查，未执行 Playwright）。
- Vite resolveConfig 实测默认和 8002 的 dev / preview 目标一致，HTTPS、回环绑定、changeOrigin=false、xfwd=true、未关闭代理 TLS 验证均断言通过；这是配置解析测试，不是 HTTP 或浏览器链路验收。
- 首次构建因 NodeNext 要求相对导入扩展名失败，改为显式 `.ts` 后完整重跑通过。
- 日志：`/workspace/competition/frontend-configurable-proxy-evidence/checks.log`。
- 本次无 UI 变更、无新增截图或 trace；没有浏览器实测，不声明 8002 健康或真实模型成功。Playwright 全链路由奶龙另行执行。
