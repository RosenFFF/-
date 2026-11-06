"""Lightweight feature hashing; optional BGE loads only local cached weights, never downloads."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


def tokens(text: str) -> list[str]:
    text = text.casefold()
    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text)
    return words + [text[i : i + 2] for i in range(len(text) - 1) if "\u4e00" <= text[i] <= "\u9fff"]


def cosine(a: list[float], b: list[float]) -> float:
    denom = math.sqrt(sum(v * v for v in a) * sum(v * v for v in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / denom if denom else 0.0


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedding:
    name = "feature-hash-128 (lightweight, not BGE)"

    def encode(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vector = [0.0] * 128
            for word in tokens(text):
                digest = hashlib.sha256(word.encode()).digest()
                vector[int.from_bytes(digest[:4]) % 128] += 1 if digest[4] & 1 else -1
            norm = math.sqrt(sum(v * v for v in vector)) or 1
            out.append([v / norm for v in vector])
        return out


class BGEEmbedding:
    def __init__(self, name: str):
        from sentence_transformers import SentenceTransformer

        self.name = name
        self.model = SentenceTransformer(name, local_files_only=True, trust_remote_code=False)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()
