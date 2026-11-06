import re

from .samples import invoice_image, invoice_pdf


async def _upload(c, data, name="invoice.png", mime="image/png"):
    return await c.post(
        "/api/v1/documents", files={"file": (name, data, mime)}, data={"doc_type": "commercial_invoice"}
    )


async def test_upload_png_runs_real_ocr_with_normalized_bbox(api):
    c = await api.login("reviewer")
    r = await _upload(c, invoice_image())
    assert r.status_code == 202, r.text
    doc = r.json()
    # inline 模式下后台任务在响应完成前已执行完
    d = (await c.get(f"/api/v1/documents/{doc['id']}")).json()
    assert d["status"] == "ready" and d["progress"] == 100 and d["pages"] == 1

    rec = (await c.get(f"/api/v1/documents/{doc['id']}/recognition")).json()
    blocks = rec["ocr"]["blocks"]
    text = " ".join(b["text"] for b in blocks).upper()
    assert "INVOICE" in text and re.search(r"SR-?2026-?001", text.replace(" ", ""))
    for b in blocks:
        assert b["page"] == 1 and len(b["bbox"]) == 4
        x0, y0, x1, y1 = b["bbox"]
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
        assert 0 <= b["confidence"] <= 1
    assert rec["models"][0]["category"] == "ocr"


async def test_multi_page_pdf_and_page_images(api):
    c = await api.login("reviewer")
    doc = (await _upload(c, invoice_pdf(2), "inv.pdf", "application/pdf")).json()
    d = (await c.get(f"/api/v1/documents/{doc['id']}")).json()
    assert d["status"] == "ready" and d["pages"] == 2
    blocks = (await c.get(f"/api/v1/documents/{doc['id']}/recognition")).json()["ocr"]["blocks"]
    assert {b["page"] for b in blocks} == {1, 2}
    img = await c.get(f"/api/v1/documents/{doc['id']}/pages/2/image")
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    assert img.headers["Cache-Control"] == "no-store"
    assert (await c.get(f"/api/v1/documents/{doc['id']}/pages/3/image")).status_code == 404


async def test_files_are_encrypted_at_rest(api):
    c = await api.login("reviewer")
    data = invoice_image()
    doc = (await _upload(c, data)).json()
    root = api.settings.storage_dir / doc["id"]
    for f in root.iterdir():
        raw = f.read_bytes()
        assert not raw.startswith(b"\x89PNG") and data not in raw


async def test_rejects_disguised_file_type(api):
    c = await api.login("reviewer")
    r = await _upload(c, b"MZ\x90\x00 not really an image", "invoice.png", "image/png")
    assert r.status_code == 415 and r.json()["code"] == "FILE_TYPE_UNSUPPORTED"


async def test_rejects_pdf_with_javascript(api):
    c = await api.login("reviewer")
    evil = invoice_pdf(1).replace(b"%%EOF", b"<< /Type /Action /S /JavaScript /JS (app.alert(1)) >>\n%%EOF")
    r = await _upload(c, evil, "evil.pdf", "application/pdf")
    assert r.status_code == 415


async def test_rejects_too_large_and_too_many_pages(make_api):
    api = await make_api(max_upload_bytes=50_000, max_pages=2)
    c = await api.login("reviewer")
    assert (await _upload(c, b"\x89PNG\r\n\x1a\n" + b"0" * 60_000)).status_code == 413
    r = await _upload(c, invoice_pdf(3), "inv.pdf", "application/pdf")
    assert r.status_code == 413 and r.json()["code"] == "FILE_TOO_LARGE"


async def test_filename_is_sanitized(api):
    c = await api.login("reviewer")
    doc = (await _upload(c, invoice_image(), "..\\..\\etc\\pass\u202ewd.png")).json()
    assert doc["filename"] == "passwd.png"


async def test_recognition_not_ready_returns_conflict(api):
    from sqlalchemy import update

    from app.db.models import Document

    c = await api.login("reviewer")
    doc = (await _upload(c, invoice_image())).json()
    async with api.app.state.db.sessionmaker() as s:
        await s.execute(update(Document).where(Document.id == doc["id"]).values(status="ocr_running"))
        await s.commit()
    r = await c.get(f"/api/v1/documents/{doc['id']}/recognition")
    assert r.status_code == 409 and r.json()["code"] == "DOCUMENT_NOT_READY"


async def test_delete_removes_ciphertext(api):
    c = await api.login("reviewer")
    doc = (await _upload(c, invoice_image())).json()
    assert (await c.delete(f"/api/v1/documents/{doc['id']}")).status_code == 204
    assert not (api.settings.storage_dir / doc["id"]).exists()
    assert (await c.get(f"/api/v1/documents/{doc['id']}")).status_code == 404


async def test_upload_rate_limited(make_api):
    api = await make_api(rl_upload_per_min=2)
    c = await api.login("reviewer")
    codes = [(await _upload(c, invoice_image())).status_code for _ in range(3)]
    assert codes == [202, 202, 429]
