"""Only CI/test fixtures use this fake. Production runtime never imports it."""

import json
from pathlib import Path

from app.ai.types import LLMResult, trace

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
            schema.model_validate(data), [trace("llm", "test-fixture-only", task, 1, provider="fake")], "L0"
        )

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
