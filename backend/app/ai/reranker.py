"""Lexical reranking is an explicit lightweight fallback, not a neural-model claim."""

from __future__ import annotations

from app.ai.embedding import tokens


class LexicalReranker:
    name = "token-overlap-v1 (lightweight, not BGE)"

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = set(tokens(query))
        return [len(q & set(tokens(t))) / max(1, len(q | set(tokens(t)))) for t in texts]


class BGEReranker:
    def __init__(self, name: str):
        from sentence_transformers import CrossEncoder

        self.name = name
        self.model = CrossEncoder(name, local_files_only=True, trust_remote_code=False)

    def score(self, query: str, texts: list[str]) -> list[float]:
        return self.model.predict([(query, text) for text in texts]).reshape(-1).tolist()
