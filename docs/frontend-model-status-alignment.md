# 前端 · 模型状态与降级契约对齐（demo-ready）

基线：main `a437305`（后端代码）；后端证据 `feat/backend-llm-e2e @ 831cbe8`
`reports/progress/backend-llm-e2e/model-probe.json`（`real_inference_verified=false`，`real_sse_success_verified=false`）。

## 实测 `GET /api/v1/system/models`（2026-11-06，本机 fixture，无密钥）
```json
{
  "degrade_level": "L3",
  "llm_provider_chain": ["deepseek", "qwen", "ollama"],
  "models": [
    {"category":"ocr","provider":"local","model":"rapidocr-ppocrv4","deployment":"local","stage":"单证识别","healthy":true,"circuit_open":false,"p95_latency_ms":null,"calls_24h":0},
    {"category":"llm","provider":"deepseek","model":"deepseek-chat","deployment":"cloud","healthy":false, "...": "..."},
    {"category":"llm","provider":"qwen","model":"qwen-plus","deployment":"cloud","healthy":false},
    {"category":"llm","provider":"ollama","model":"qwen2.5:7b","deployment":"local","healthy":false},
    {"category":"embedding","provider":"local","model":"feature-hash-128 (lightweight, not BGE)","healthy":true,"lightweight":true,"retrieval_mode":"lightweight_hash","implementation_mode":"lightweight_hash","mode_label":"轻量回退（非 BGE 神经模型）","configured_model":"BAAI/bge-m3","heavy_load_failed":false},
    {"category":"reranker","provider":"local","model":"token-overlap-v1 (lightweight, not BGE)","healthy":true,"lightweight":true,"retrieval_mode":"lightweight_hash","implementation_mode":"lightweight_lexical","mode_label":"轻量回退（非 BGE 神经模型）","configured_model":"BAAI/bge-reranker-v2-m3"}
  ]
}
```
与 831cbe8 `model-probe.json.system_models` 结构一致（L3、三个 LLM 均 `healthy=false`）。差异仅为 Ollama 型号配置：本 fixture 用后端默认 `qwen2.5:7b`，probe 用 `qwen2.5:0.5b`；两者均未拉取。早先运行时本机 Ollama `/api/tags` → `models: []`；0f6d43c 干净克隆运行的实测探针显示 Ollama **不可达**（见 `models-probe-*.json`）。两种情况下都没有可用 LLM，均为 L3。

## 与 `docs/api.yaml` ModelChain 比对
- 字段、枚举、embedding/reranker 条件必填：**一致**，无契约偏差。
- `/system/models` 本身**不含** `degrade_status`（spec 亦无）；报告/抽取/审计中的 `degrade_status` 由前端原样显示，不再自造 L0–L3 文案。

## 追问 SSE（实测）
HTTP **200** `text/event-stream`，流内**仅** `event: error`，`data` 为 Problem：`status=503, code=MODEL_UNAVAILABLE`。与 spec「error：…status=503…绝不发送成功 delta/citation/done」一致。
前端：HTTP 200 不视为成功；`error` 事件 → `ApiError` → 「模型暂不可用」提示，无 assistant 消息。单测 `src/api/sse.test.ts`（HTTP 200 + 仅 error）。

## 前端改动
- `ModelChain` / `ModelEntry` 类型按 spec + 实测补全（`llm_provider_chain`、`lightweight`、`mode_label`、`configured_model`、`circuit_open`、`calls_24h`、`p95_latency_ms`）。
- 模型页：显示接口 `degrade_level` 与 LLM 降级顺序；全部 LLM 不健康时显示「当前无可用 LLM …503 MODEL_UNAVAILABLE，不会伪造回答」。
- 轻量检索只显示 wire `model` + `mode_label`；**不**把 `configured_model`（BAAI/bge-*）当作运行模型（`src/api/modelStatus.test.ts`）。

## 给后端的备注
无契约不一致需后端修改。仅建议：Ollama 默认型号（7b）与 probe（0.5b）统一口径后再写入路演材料。

## Models-page evidence: two separate kinds

| Kind | What it is | What it proves | Where |
|---|---|---|---|
| (a) Contract assertion (**hardcoded**) | Spec `ENVIRONMENT.ollama_expected_contract` = "/api/tags models=[]", plus UI assertions (L3 banner, no-LLM banner, lightweight ≠ BGE) | Only that the frontend **renders** the expected behaviour for this wire shape. Not a measurement. | `e2e/real-demo.spec.ts`; `run-*.json` → `evidence.contract_assertion` |
| (b) Actual probe | Raw `GET /api/v1/system/models` body captured from the fixture backend during the run, plus a live `GET {FIXTURE_OLLAMA_URL}/api/tags` | What the backend actually reported in that run (degrade_level, per-model `healthy`), whether Ollama was reachable, and which models it listed | `screenshots/demo-ready/models-probe-{390,1440}.json`; `run-*.json` → `evidence.actual_*` |

## Ollama model names

`qwen2.5:7b` (a437305 fixture config) and `qwen2.5:0.5b` (backend 831cbe8 `model-probe.json`) are **configured model names only**. Neither means the model is installed or that inference succeeded. Only `healthy` status plus real call evidence count, and the probe artifacts show which models Ollama actually lists.
