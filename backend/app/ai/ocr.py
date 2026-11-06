"""OCR 适配器：RapidOCR（PP-OCRv4 的 ONNX 版本），本地 CPU 推理，断网可用。

输出统一为文本块：text、归一化 bbox [x0,y0,x1,y1]（0–1，左上为原点）、confidence。
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(slots=True)
class OcrBlock:
    text: str
    bbox: list[float]
    confidence: float


class OcrEngine:
    name = "rapidocr-ppocrv4"

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._engine is not None

    def load(self) -> None:
        with self._lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()

    def recognize(self, png: bytes) -> tuple[list[OcrBlock], int]:
        self.load()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        w, h = img.size
        t0 = time.perf_counter()
        result, _ = self._engine(np.asarray(img))  # type: ignore[misc]
        ms = int((time.perf_counter() - t0) * 1000)
        blocks: list[OcrBlock] = []
        for quad, txt, score in result or []:
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            bbox = [round(max(0.0, min(1.0, v)), 4) for v in (min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h)]
            blocks.append(OcrBlock(str(txt), bbox, round(float(score), 4)))
        # 阅读顺序：先上后下、再左后右
        blocks.sort(key=lambda b: (round(b.bbox[1], 2), b.bbox[0]))
        return blocks, ms


ocr_engine = OcrEngine()
