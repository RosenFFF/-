import pytest
from sqlalchemy import select

from app.db.models import AuditLog
from app.security.rbac import ROLE_PERMS, Perm, Role

from .samples import invoice_image

# (方法, 路径, 角色 → 期望状态码)
MATRIX = [
    ("GET", "/api/v1/users", {"admin": 200, "reviewer": 403, "auditor": 403}),
    ("GET", "/api/v1/audit/logs", {"admin": 200, "reviewer": 403, "auditor": 200}),
    ("GET", "/api/v1/audit/verify", {"admin": 200, "reviewer": 403, "auditor": 200}),
    ("GET", "/api/v1/documents", {"admin": 200, "reviewer": 200, "auditor": 200}),
]


@pytest.mark.parametrize(("method", "path", "expect"), MATRIX)
async def test_rbac_matrix(api, method, path, expect):
    for role, code in expect.items():
        c = await api.login(role)
        r = await c.request(method, path)
        assert r.status_code == code, (role, path, r.text)


async def test_denied_access_is_audited_and_visible_to_security_admin(api):
    rev = await api.login("reviewer")
    r = await rev.get("/api/v1/audit/logs")
    assert r.status_code == 403 and r.json()["code"] == "PERMISSION_DENIED"
    aud = await api.login("auditor")
    items = (await aud.get("/api/v1/audit/logs", params={"action": "access.denied"})).json()["items"]
    assert items and items[0]["actor_username"] == "reviewer"
    assert items[0]["detail"]["required"] == "audit:read_all"


async def test_auditor_cannot_upload(api):
    c = await api.login("auditor")
    r = await c.post("/api/v1/documents", files={"file": ("a.png", invoice_image(), "image/png")})
    assert r.status_code == 403
    async with api.app.state.db.sessionmaker() as s:
        assert (await s.execute(select(AuditLog).where(AuditLog.action == "document.upload"))).first() is None


async def test_reviewer_cannot_see_other_reviewers_document(api):
    owner = await api.login("reviewer")
    doc = (await owner.post("/api/v1/documents", files={"file": ("a.png", invoice_image(), "image/png")})).json()
    other = await api.login("reviewer2")
    assert (await other.get(f"/api/v1/documents/{doc['id']}")).status_code == 404
    assert (await other.delete(f"/api/v1/documents/{doc['id']}")).status_code == 404
    assert (await other.get("/api/v1/documents")).json()["total"] == 0
    auditor = await api.login("auditor")
    assert (await auditor.get(f"/api/v1/documents/{doc['id']}")).status_code == 200


def test_role_permission_table_is_least_privilege():
    assert Perm.audit_read_all not in ROLE_PERMS[Role.reviewer]
    assert Perm.document_upload not in ROLE_PERMS[Role.auditor]
    assert Perm.user_manage not in ROLE_PERMS[Role.auditor]
