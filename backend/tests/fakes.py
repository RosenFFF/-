"""Only CI/test fixtures use this fake. Production runtime never imports it."""

import json
from pathlib import Path

from app.ai.types import LLMResult, ModelUnavailable, TextChunk, trace

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


class FakeLLM:
    def __init__(self, *, invalid_citation=False, unavailable=False):
        self.messages = []
        self.invalid_citation = invalid_citation
        self.unavailable = unavailable

    async def chat_json(self, messages, schema, *, task):
        self.messages.append((task, messages))
        if self.unavailable:
            return LLMResult(None, [], "L3")
        data = json.loads(
            (FIXTURES / ("extraction.json" if task == "field_extraction" else "reasoning.json")).read_text()
        )
        if task == "compliance_reasoning":
            given = json.loads(messages[-1]["content"])["allowed_rules"]
            data["findings"][0]["rule_ids"] = ["NONEXISTENT" if self.invalid_citation else given[0]["rule_id"]]
        return LLMResult(
            schema.model_validate(data),
            [trace("llm", "test-fixture-only", task, 1, provider="fake", degrade_level="L0")],
            "L0",
        )

    async def chat_stream(self, messages, *, task="chat"):
        """仅测试：fixture text and model identity can NEVER count as real model evidence."""
        self.messages.append((task, messages))
        if self.unavailable:
            raise ModelUnavailable()
        given = json.loads(messages[-1]["content"])["allowed_rules"]
        rule_id = "NONEXISTENT" if self.invalid_citation else given[0]["rule_id"]
        text = "TEST FIXTURE ONLY: Review this summary with a human. " + f"[{rule_id}]"
        for offset in range(0, len(text), 7):
            yield TextChunk(text=text[offset : offset + 7])
        yield TextChunk(
            finished=True, traces=[trace("llm", "test-fixture-only", task, 1, provider="fake", degrade_level="L0")]
        )

    async def chat_text(self, messages, *, task="chat"):
        text, traces = "", []
        try:
            async for chunk in self.chat_stream(messages, task=task):
                text += chunk.text
                traces = chunk.traces or traces
        except ModelUnavailable as exc:
            return LLMResult(None, exc.traces, "L3")
        return LLMResult(text, traces, "L0")

    async def health(self):
        return [
            {
                "category": "llm",
                "provider": "fake",
                "model": "test-fixture-only",
                "deployment": "local",
                "stage": "tests only",
                "healthy": not self.unavailable,
                "circuit_open": False,
                "p95_latency_ms": 1,
                "calls_24h": len(self.messages),
            }
        ]
