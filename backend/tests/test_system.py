async def test_healthz_and_security_headers(api):
    async with api.client() as c:
        r = await c.get("/api/v1/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert len(r.headers["X-Request-ID"]) >= 8


async def test_request_id_is_echoed_only_if_well_formed(api):
    async with api.client() as c:
        good = await c.get("/api/v1/healthz", headers={"X-Request-ID": "abc-12345678"})
        bad = await c.get("/api/v1/healthz", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert good.headers["X-Request-ID"] == "abc-12345678"
    assert "<" not in bad.headers["X-Request-ID"]


async def test_readyz_reports_dependencies_and_degrade_level(api):
    async with api.client() as c:
        r = await c.get("/api/v1/readyz")
    body = r.json()
    assert r.status_code == 200
    assert body["checks"]["database"]["ok"] and body["checks"]["redis"]["ok"]
    assert body["status"] == "degraded" and body["degrade_level"] == "L3"  # M0 尚未接 LLM，如实报告


async def test_system_models_requires_login_and_lists_model_chain(api):
    async with api.client() as anon:
        assert (await anon.get("/api/v1/system/models")).status_code == 401
    c = await api.login("reviewer")
    body = (await c.get("/api/v1/system/models")).json()
    cats = {m["category"] for m in body["models"]}
    assert {"ocr", "llm", "embedding", "reranker"} <= cats


async def test_errors_are_problem_json_without_stack(api):
    async with api.client() as c:
        r = await c.post("/api/v1/auth/login", json={"username": "x"})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "VALIDATION_FAILED" and body["request_id"] and body["errors"]
