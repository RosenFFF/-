"""Immutable process-local rule index, seeded at API/worker startup. No external text ingestion."""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.ai.embedding import BGEEmbedding, cosine
from app.ai.types import trace
from app.services.provenance import SOURCE_KIND_LABELS, is_public, provenance, source_kind_of_rule


class RuleIndex:
    def __init__(self, directory: Path, embedding, reranker):
        self.embedding, self.reranker = embedding, reranker
        self.rules: dict[str, dict] = {}
        self.chunks: list[dict] = []
        for path in sorted(directory.glob("*.json")):
            for rule in json.loads(path.read_text(encoding="utf-8")):
                if rule["id"] in self.rules:
                    raise ValueError("duplicate rule id")
                self.rules[rule["id"]] = rule
                text = rule["title"] + "\n" + rule["text"]
                for start in range(0, len(text), 500):
                    self.chunks.append({"rule_id": rule["id"], "text": text[start : start + 600]})
        self.vectors = embedding.encode([c["text"] for c in self.chunks])
        self.healthy = bool(self.rules)

    @property
    def retrieval_mode(self) -> str:
        return "bge" if isinstance(self.embedding, BGEEmbedding) else "lightweight_hash"

    def security(self, citations: list[dict] | None = None) -> dict:
        # Recognition shows the configured index; review shows the actual supplied citations.
        return provenance(list(self.rules.values()) if citations is None else citations, self.retrieval_mode)

    def detail(self, rule_id: str) -> dict | None:
        """Public rule card: same provenance fields as citations, never raw seed-only shape."""
        r = self.rules.get(rule_id)
        if r is None:
            return None
        kind = source_kind_of_rule(r)
        return {
            "id": r["id"],
            "source": r["source"],
            "jurisdiction": r["jurisdiction"],
            "article": r["article"],
            "title": r["title"],
            "text": r["text"],
            "url": r.get("url"),
            "effective_date": r.get("effective_date"),
            "corpus": "public_verified" if is_public(r) else "synthetic",
            "verified_at": r.get("verified_at"),
            "verification_note": r.get("verification_note"),
            "source_kind": kind,
            "source_kind_label": SOURCE_KIND_LABELS[kind],
            "version_date": r.get("verified_at") or r.get("effective_date"),
            "excerpt_kind": "summary",
            "applicability": "unverified",
        }

    def citation(self, rule_id: str, score: float = 1.0) -> dict:
        r = self.rules[rule_id]
        return {
            "rule_id": r["id"],
            "source": r["source"],
            "jurisdiction": r["jurisdiction"],
            "article": r["article"],
            "excerpt": r["text"],
            "url": r.get("url"),
            "score": round(score, 5),
            "corpus": "public_verified" if is_public(r) else "synthetic",
            "source_kind": source_kind_of_rule(r),
            "source_kind_label": SOURCE_KIND_LABELS[source_kind_of_rule(r)],
            "verified_at": r.get("verified_at"),
            "effective_date": r.get("effective_date"),
            "version_date": r.get("verified_at") or r.get("effective_date"),
            "excerpt_kind": "summary",  # 公开条目为摘要，非法规原文
            "applicability": "unverified",  # 不构成完整适用性证据
        }

    def search(self, query: str, top_k: int = 20, top_n: int = 5) -> tuple[list[dict], list[dict]]:
        t0 = time.perf_counter()
        vector = self.embedding.encode([query])[0]
        ranked = sorted(range(len(self.chunks)), key=lambda i: cosine(vector, self.vectors[i]), reverse=True)[:top_k]
        embed_ms = int((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        scores = self.reranker.score(query, [self.chunks[i]["text"] for i in ranked])
        selected = sorted(zip(ranked, scores, strict=True), key=lambda pair: pair[1], reverse=True)
        unique = {}
        for i, score in selected:
            rid = self.chunks[i]["rule_id"]
            if rid not in unique:
                unique[rid] = self.citation(rid, score)
            if len(unique) >= top_n:
                break
        return list(unique.values()), [
            trace("embedding", self.embedding.name, "rule_retrieval", embed_ms),
            trace("reranker", self.reranker.name, "rerank", int((time.perf_counter() - t0) * 1000)),
        ]
