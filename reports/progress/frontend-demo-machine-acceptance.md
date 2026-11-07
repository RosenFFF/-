# 演示机 Playwright 用例交付（未执行浏览器）

基线为 71311f4，包含前序可配置代理提交 2073eb4。本轮只改前端验收脚本、辅助脱敏工具、测试和文档；未改 UI、后端、密钥文件或历史归档，未运行任何浏览器或绕过平台策略。

## 内容

- `web/playwright.demo-machine.config.ts`：显式演示机开关、前后端地址环境变量、生产 dist 的 HTTPS preview、mock 关闭、单 worker 零重试；拒绝复用不明端口和忽略 TLS 错误。
- `web/e2e/demo-machine.spec.ts`：登录→上传合成 PDF→识别→完成审查→三轮 SSE 追问，其中第二轮为宽泛问题。严格检查 report L0 / llm_verified、SSE done/非阻断非空内容及无 error；保留逐步截图和错误计数。HTTP 200 不等于成功。
- HAR 仅白名单元数据；trace 从登录后录制，并离线白名单脱敏；原始包只写私有临时目录、随后删除。不发布认证体、Cookie、网络体、源码或原始浏览器错误。截图仅用合成材料，演示机发布前仍需人工复查。
- 普通 mock Playwright 配置排除演示机用例；专用 npm 命令先进行类型检查。新配置也已纳入 tsconfig.e2e。
- `docs/demo-machine-acceptance.md`：演示机准备、受信任 HTTPS、环境变量、独立证据目录、预算控制、运行方法、失败条件与证据局限。

## 已完成检查

oxlint、Vitest 10 文件 / 124 测试、tsc -b、Vite build、prod-no-mock、prod-no-demo、tsc -p tsconfig.e2e.json 全部通过。Python trace 白名单脱敏测试 1 项通过。日志：`/workspace/competition/frontend-demo-machine-acceptance-evidence-20261107T0124/final-checks.log`。

## 未验收项

**平台策略限制，不可在本机执行浏览器链路**。本轮未执行 Playwright / Chromium，未生成新浏览器截图、HAR、trace 或成功结论。演示机真实链路、trace viewer 可读性、人工脱敏复查、准确率/P95和恢复演练均不由这些静态/单元检查证明。宽泛追问若在演示机失败必须记录为真实失败，不声称 BGE 或整体稳定。
