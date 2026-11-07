# 路演实测表 · 前端部分（demo-ready）

> **⚠ Label: dev server (vite), SQLite/fakeredis stand-ins, n=1 per viewport — not production performance or full-stack acceptance.**


来源骨架：`feat/coord-m3-docs @ 76854ab` `docs/submission/路演脚本.md`「二附、路演实测表」与 `项目作品说明文档.md` §6.1（main `a437305` docs 内无该表；本文件未修改协调分支）。
仅填**实测**值；未测项留空并写原因。禁止 MOCK/FakeLLM 数值。

## 环境（如实）
| 项 | 值 |
|---|---|
| 后端代码 | main `a437305`（独立 worktree，未改代码） |
| 后端模型证据 | `feat/backend-llm-e2e @ 831cbe8` model-probe：`real_inference_verified=false` |
| 运行方式 | `web/e2e/real-backend-fixture (in-repo)/serve_fixture`（`tests.conftest._seed` 经 `tenant_session` 播种；存在性检查用 `maintenance_sessionmaker`；租户门禁开启） |
| 数据库 | **SQLite 替身**（非 PostgreSQL） |
| Redis | **fakeredis 替身**（非 Redis 8） |
| LLM | deepseek/qwen 无密钥；Ollama：实测探针（models-probe-*.json）显示本次 `127.0.0.1:11434` **不可达**（fetch failed；早先 5d3abdb 时期曾可达且 `models: []`）→ 全部 LLM `healthy=false`，`degrade_level=L3` |
| Embedding/Reranker | 轻量回退（feature-hash-128 / token-overlap-v1），**非 BGE** |
| 前端 | `feat/frontend-demo-ready`，vite dev（HTTPS localhost，`VITE_USE_MOCK` 未设置），Chromium headless |
| 限流 | fixture `FIXTURE_RL_DEFAULT_PER_MIN=30`（为跑通整链；M2 429 演示用默认 2） |
| 样例 | 自制脱敏 PDF `screenshots/m1/_real-invoice.pdf`（1 页） |
| 次数 | 每视口 1 次（n=1，**非 P95**） |

## 前端实测
| 指标 | 口径 | 390×844 | 1440×900 | 档位 | 证据 |
|---|---|---|---|---|---|
| 页面加载 | `/login` Navigation Timing `loadEventEnd`（dev 服务，非生产包） | 320 ms | 251 ms | — | `screenshots/demo-ready/at-0f6d43c/run-*.json` |
| 上传→识别结果 | 点「开始识别」→ 抽取页校验条可见 | 2221 ms | 2225 ms | L3 | 同上 |
| 审查 | 点「发起审查」→ 报告完成（「继续追问」出现） | 1398 ms | 1394 ms | L3（规则引擎回退，`llm_verified=false`） | 同上 |
| 追问 | 发送 → 前端显示「模型暂不可用」 | 159 ms | 165 ms | L3：HTTP 200 SSE 仅 `error` 503 `MODEL_UNAVAILABLE`，无 assistant 消息 | `ask-*.json` |
| 审计 | 管理员打开 `/audit` → 全局看板 | 389 ms | 349 ms | — | `audit-admin-*.json` |
| 模型状态显示 | `/system/models` 打开 → 等级渲染 | 261 ms；显示 L3、三 LLM 不可用、「当前无可用 LLM」、轻量非 BGE | 241 ms；同左 | L3 | `models-*.json` |
| 390/1440 | 7 个页面横向溢出 | 无 | 无 | — | 各页 sidecar |
| a11y | axe violations / 未决对比度 | 0 / 0（7 页） | 0 / 0（7 页） | — | 各页 sidecar |

## 留空项（原因）
| 指标 | 原因 |
|---|---|
| 端到端 P95（单页上传→报告） | n=1，且 L3 规则回退、非真模型；不可当作 P95 |
| 真模型追问流式首字/完成时延 | 真模型不可用（831cbe8：`real_sse_success_verified=false`） |
| 字段 F1 / Recall@5 / 引用准确率 / 消融 | 属后端评测；真 LLM 与 BGE 未就绪，前端不填 |
| PostgreSQL/Redis 活库下的前端时延 | 本次用 SQLite/fakeredis 替身 |
| 生产包加载时延 | 本次为 vite dev；生产包未在真后端前跑 |
| 断网降级演示 | 未测 |

**Provenance of the numbers above:** clean clone of the bundle at **0f6d43c** + fresh a437305 backend worktree, in-repo `scripts/run-real-demo-e2e.sh`, one run per viewport (artifacts: `screenshots/demo-ready/at-0f6d43c/`). Later commits change only docs and the spec's hardcoded expectation text. The final tip's own clean-clone rerun is in `screenshots/demo-ready/` (run-*.json); its numbers differ by run-to-run noise (n=1).

**Actual probe result (0f6d43c run, both viewports):** HTTP 200 and `degrade_level` L3.

- OCR rapidocr-ppocrv4 is healthy.
- The LLMs deepseek-chat, qwen-plus and qwen2.5:7b are all `healthy=false`.
- Embedding feature-hash-128 and reranker token-overlap-v1 are healthy, marked lightweight, not BGE.
- Ollama at `127.0.0.1:11434` was **unreachable** (fetch failed).

So the hardcoded contract expectation ("models=[]") did **not** literally match this run. The UI outcome (L3, no-LLM banner) is the same, because both states leave no usable LLM.

## Models-page evidence: two separate kinds

| Kind | What it is | What it proves | Where |
|---|---|---|---|
| (a) Contract assertion (**hardcoded**) | Spec `ENVIRONMENT.ollama_expected_contract` = "/api/tags models=[]", plus UI assertions (L3 banner, no-LLM banner, lightweight ≠ BGE) | Only that the frontend **renders** the expected behaviour for this wire shape. Not a measurement. | `e2e/real-demo.spec.ts`; `run-*.json` → `evidence.contract_assertion` |
| (b) Actual probe | Raw `GET /api/v1/system/models` body captured from the fixture backend during the run, plus a live `GET {FIXTURE_OLLAMA_URL}/api/tags` | What the backend actually reported in that run (degrade_level, per-model `healthy`), whether Ollama was reachable, and which models it listed | `screenshots/demo-ready/models-probe-{390,1440}.json`; `run-*.json` → `evidence.actual_*` |

## Ollama model names

`qwen2.5:7b` (a437305 fixture config) and `qwen2.5:0.5b` (backend 831cbe8 `model-probe.json`) are **configured model names only**. Neither means the model is installed or that inference succeeded. Only `healthy` status plus real call evidence count, and the probe artifacts show which models Ollama actually lists.
