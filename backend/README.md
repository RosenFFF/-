# 丝路智审 · 后端

FastAPI + PostgreSQL(pgvector) + Redis + arq，OCR 用本地 RapidOCR（PP-OCRv4 ONNX）。接口契约见 `../docs/api.yaml`，架构见 `../docs/architecture.md`。

## 一键启动（Docker Compose）

```bash
cp .env.example .env          # 在仓库根目录；按注释生成并填写 JWT_SECRET、DATA_KEK、数据库与 Redis 密码、初始管理员密码
docker compose up -d --build
curl http://127.0.0.1:8000/api/v1/readyz
```

本地大模型（M1 起用）：`docker compose --profile local-llm up -d`。

创建其他账号（密码交互输入，不进命令历史）：

```bash
docker compose exec api python -m app.cli create-user --username reviewer1 --role reviewer
```

## 本地开发与测试

```bash
cd backend
uv sync
uv run ruff check app tests
uv run pytest -q          # SQLite + fakeredis + 真实 RapidOCR，不需要 Docker
```

`requirements.txt` 由 `uv export --frozen --no-dev --no-emit-project` 从 `uv.lock` 导出，供依赖漏洞扫描使用；改依赖后请重新导出。

## 安全要点

- 会话令牌只在 HttpOnly + Secure + SameSite=Strict Cookie 中；写请求需 `X-CSRF-Token`。
- 密码 Argon2id；登录限流 + 连续失败锁定；刷新令牌轮换与重放检测。
- RBAC（admin / reviewer / auditor）+ 对象级授权，越权访问返回 404 并记审计。
- 上传文件校验魔数、拒绝含脚本的 PDF、限制大小与页数；落盘 AES-256-GCM 信封加密。
- 审计日志哈希链，`/api/v1/audit/verify` 可定位被篡改的记录；演示篡改端点仅在 `DEMO_MODE=true` 时存在。
