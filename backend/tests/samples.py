"""测试用合成单证（不含任何真实个人或企业信息）。"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

LINES = ["COMMERCIAL INVOICE", "INVOICE NO: SR-2026-001", "TOTAL: USD 12,500.00"]


def invoice_image(fmt: str = "PNG", lines: list[str] | None = None) -> bytes:
    img = Image.new("RGB", (1200, 700), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=56)
    for i, line in enumerate(lines or LINES):
        d.text((60, 80 + i * 180), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def invoice_pdf(pages: int = 2) -> bytes:
    imgs = [Image.open(io.BytesIO(invoice_image(lines=[f"PAGE {i + 1}", *LINES[1:]]))) for i in range(pages)]
    buf = io.BytesIO()
    imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:])
    return buf.getvalue()
