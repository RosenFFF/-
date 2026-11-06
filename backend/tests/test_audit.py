async def test_hash_chain_valid_after_activity(api):
    await api.login("reviewer")
    aud = await api.login("auditor")
    r = (await aud.get("/api/v1/audit/verify")).json()
    assert r["valid"] and r["checked"] >= 2 and r["first_broken_id"] is None


async def test_demo_tamper_is_detected_and_restorable(api):
    rev = await api.login("reviewer")
    await rev.get("/api/v1/audit/logs")  # 产生一条越权记录
    admin = await api.login("admin")
    logs = (await admin.get("/api/v1/audit/logs", params={"action": "access.denied"})).json()["items"]
    target = logs[0]["id"]

    assert (await admin.post("/api/v1/demo/audit/tamper", json={"log_id": target})).status_code == 200
    v = (await admin.get("/api/v1/audit/verify")).json()
    assert v["valid"] is False and v["first_broken_id"] == target

    assert (await admin.post("/api/v1/demo/audit/restore", json={"log_id": target})).status_code == 200
    assert (await admin.get("/api/v1/audit/verify")).json()["valid"] is True


async def test_demo_tamper_admin_only(api):
    rev = await api.login("reviewer")
    r = await rev.post("/api/v1/demo/audit/tamper", json={"log_id": "0" * 36})
    assert r.status_code == 403


async def test_demo_endpoints_absent_when_demo_mode_off(make_api):
    api = await make_api(demo_mode=False)
    admin = await api.login("admin")
    r = await admin.post("/api/v1/demo/audit/tamper", json={"log_id": "0" * 36})
    assert r.status_code == 404


async def test_audit_ip_is_masked(api):
    aud = await api.login("auditor")
    items = (await aud.get("/api/v1/audit/logs", params={"action": "auth.login"})).json()["items"]
    assert all(i["ip"] is None or i["ip"].endswith("*") for i in items)
