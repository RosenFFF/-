# M2 审计篡改/恢复演示（仅合成夹具，非真实模型验收）

## 可复现测试

在 backend 目录执行：

```bash
uv run pytest -q tests/test_audit.py::test_demo_tamper_is_detected_and_restorable \
  tests/test_audit.py::test_demo_tamper_admin_only \
  tests/test_m2_openapi.py::test_production_has_no_demo_routes_even_if_demo_flag_misconfigured
```

测试使用 conftest 生成的临时 SQLite、fakeredis 和合成账号，不连接生产/真实模型，不需提供密钥；不在报告中打印 Cookie/密码。初始表由 Alembic 迁移创建。

1. 合成 reviewer 请求 `/audit/logs`，返回403并追加 access.denied。
2. 合成 admin 获取本租户 access.denied 的日志 ID。
3. `POST /api/v1/demo/audit/tamper`，JSON 为 `{"log_id":"<该日志 UUID>"}`。须 admin、合法会话 CSRF/Origin；保存原始 detail 备份，再修改 detail 而故意不重算 hash。
4. `GET /api/v1/audit/verify` 返回 `valid=false`，`first_broken_id` 为目标 ID。
5. `POST /api/v1/demo/audit/restore`，相同 log_id；恢复备份原文并删除该条演示备份，校验返回 valid=true。tamper/restore 自身追加审计，不删除业务审计。

## 演示环境边界

只在 `ENV != prod` 且 `DEMO_MODE=true` 注册这两个演示写接口；ENV=prod 时即使误设 DEMO_MODE=true 也没有路径。reviewer 调用403；外租户 log_id 为404；DEMO_MODE=false 时404。不要以停用 CSRF/Secure Cookie 演示，不要对共享/生产审计链操作。

这是哈希链完整性演示，不证明管理员无法重算整链，不证明真实 LLM/检索主链路已验收。生产数据库迁移、备份与权限应独立审查。
