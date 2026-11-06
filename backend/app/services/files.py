"""上传文件校验与渲染：按魔数判断真实类型、限制大小和页数、拒绝带脚本的 PDF、防解压炸弹。"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

import pypdfium2 as pdfium
from PIL import Image

from app.core.errors import AppError

Image.MAX_IMAGE_PIXELS = 50_000_000  # 防解压炸弹

_MAGIC = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}
# 出现这些对象的 PDF 一律拒收（脚本、自动动作、嵌入文件、外部启动）
_PDF_DANGEROUS = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA|RichMedia|XFA)\b")
RENDER_SCALE = 2.0  # 约 144 DPI，兼顾识别率与速度


@dataclass(slots=True)
class Inspected:
    mime: str
    pages: int


def sniff(data: bytes) -> str:
    for magic, mime in _MAGIC.items():
        if data.startswith(magic):
            return mime
    raise AppError(415, "FILE_TYPE_UNSUPPORTED", "只支持 PDF、PNG、JPEG 文件")


def inspect(data: bytes, max_pages: int) -> Inspected:
    mime = sniff(data)
    if mime == "application/pdf":
        if _PDF_DANGEROUS.search(data):
            raise AppError(415, "FILE_TYPE_UNSUPPORTED", "PDF 含脚本或嵌入对象，已拒收")
        try:
            pdf = pdfium.PdfDocument(data)
            n = len(pdf)
            pdf.close()
        except pdfium.PdfiumError as e:
            raise AppError(415, "FILE_TYPE_UNSUPPORTED", "PDF 无法解析") from e
    else:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except (OSError, Image.DecompressionBombError) as e:
            raise AppError(415, "FILE_TYPE_UNSUPPORTED", "图片无法解析") from e
        n = 1
    if n < 1 or n > max_pages:
        raise AppError(413, "FILE_TOO_LARGE", f"页数超过上限（{max_pages} 页）")
    return Inspected(mime, n)


def render_pages(data: bytes, mime: str) -> list[bytes]:
    """统一渲染成 PNG（去掉原图元数据，例如 EXIF 中的定位信息）。"""
    out: list[bytes] = []
    if mime == "application/pdf":
        pdf = pdfium.PdfDocument(data)
        try:
            for page in pdf:
                img = page.render(scale=RENDER_SCALE).to_pil()
                out.append(_png(img))
        finally:
            pdf.close()
    else:
        with Image.open(io.BytesIO(data)) as im:
            out.append(_png(im.convert("RGB")))
    return out


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def clean_filename(name: str | None) -> str:
    """展示用文件名：去路径、去控制字符、限长。存储路径不使用文件名。"""
    name = (name or "document").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in unicodedata.normalize("NFC", name) if unicodedata.category(ch)[0] != "C")
    return name.strip()[:120] or "document"
