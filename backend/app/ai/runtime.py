from __future__ import annotations

from app.ai.embedding import BGEEmbedding, HashEmbedding
from app.ai.llm import ProviderChain
from app.ai.reranker import BGEReranker, LexicalReranker
from app.core.config import Settings
from app.services.rag import RuleIndex


class AIRuntime:
    def __init__(self, settings: Settings, *, llm=None):
        self.settings = settings
        self.llm = llm or ProviderChain(settings)
        self.embedding = HashEmbedding()
        self.reranker = LexicalReranker()
        self.heavy_error = False
        if settings.heavy_models_enabled:
            try:
                embedding = BGEEmbedding(settings.embedding_model)
                reranker = BGEReranker(settings.reranker_model)
                self.embedding, self.reranker = embedding, reranker
            except (ImportError, OSError, ValueError, RuntimeError):
                self.heavy_error = True  # Fail visibly; do not disguise fallback as BGE.
        self.rag = RuleIndex(settings.rules_dir, self.embedding, self.reranker)

    async def health(self) -> tuple[str, list[dict]]:
        items = await self.llm.health()
        healthy = [(i, p) for i, p in enumerate(items) if p["healthy"]]
        if not healthy:
            level = "L3"
        else:
            index, p = healthy[0]
            level = "L2" if p["provider"] == "ollama" else ("L1" if index else "L0")
        for category, engine in (("embedding", self.embedding), ("reranker", self.reranker)):
            items.append(
                {
                    "category": category,
                    "provider": "local",
                    "model": engine.name,
                    "deployment": "local",
                    "stage": "规则检索" if category == "embedding" else "条款精排",
                    "healthy": self.rag.healthy,
                    "lightweight": isinstance(engine, (HashEmbedding, LexicalReranker)),
                    "retrieval_mode": self.rag.retrieval_mode,
                    "implementation_mode": (
                        "lightweight_hash"
                        if isinstance(engine, HashEmbedding)
                        else "lightweight_lexical"
                        if isinstance(engine, LexicalReranker)
                        else "bge"
                    ),
                    "mode_label": (
                        "轻量回退（非 BGE 神经模型）"
                        if isinstance(engine, (HashEmbedding, LexicalReranker))
                        else "BGE 本地神经模型"
                    ),
                    "configured_model": self.settings.embedding_model
                    if category == "embedding"
                    else self.settings.reranker_model,
                    "heavy_load_failed": self.heavy_error,
                    "circuit_open": False,
                    "p95_latency_ms": None,
                    "calls_24h": 0,
                }
            )
        return level, items
