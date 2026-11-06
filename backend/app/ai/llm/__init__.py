"""OpenAI-compatible provider chain, strict JSON outputs, bounded retries and circuits.

No prompt, response body, authorization header or exception text is logged here.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.types import LLMResult, ModelUnavailable, TextChunk, trace
from app.core.config import Settings
from app.security.output import unsafe_output


class LLMClient(Protocol):
    async def chat_json(self, messages: list[dict], schema: type[BaseModel], *, task: str) -> LLMResult: ...
    def chat_stream(self, messages: list[dict], *, task: str) -> AsyncIterator[TextChunk]: ...
    async def chat_text(self, messages: list[dict], *, task: str) -> LLMResult: ...
    async def health(self) -> list[dict]: ...


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    key: str | None = field(repr=False)
    failures: int = 0
    opened_at: float = 0
    healthy: bool = False
    checked_at: float = 0
    calls: deque = field(default_factory=lambda: deque(maxlen=2000))

    def circuit_open(self, settings: Settings) -> bool:
        return (
            self.failures >= settings.llm_circuit_failures
            and time.monotonic() - self.opened_at < settings.llm_circuit_reset_s
        )

    @property
    def available(self) -> bool:
        return self.name == "ollama" or bool(self.key)

    @property
    def api_url(self) -> str:
        base = self.base_url.rstrip("/")
        return base if base.endswith("/v1") else base + "/v1"


def level(provider: str, index: int) -> str:
    return "L2" if provider == "ollama" else ("L0" if index == 0 else "L1")


class ProviderChain:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
        all_providers = {
            "deepseek": Provider(
                "deepseek", settings.deepseek_base_url, settings.deepseek_model, settings.deepseek_api_key
            ),
            "qwen": Provider("qwen", settings.qwen_base_url, settings.qwen_model, settings.qwen_api_key),
            "ollama": Provider("ollama", settings.ollama_base_url, settings.ollama_model, None),
        }
        self.providers = [all_providers[p] for p in settings.llm_provider_chain]

    async def chat_json(self, messages: list[dict], schema: type[BaseModel], *, task: str) -> LLMResult:
        traces = []
        s = self.settings
        if sum(len(m.get("content", "")) for m in messages) > s.llm_max_input_chars:
            return LLMResult(None, [], "L3")
        instruction = {
            "role": "system",
            "content": "Return ONLY a JSON object conforming to this schema: " + json.dumps(schema.model_json_schema()),
        }
        for index, provider in enumerate(self.providers):
            if not provider.available or provider.circuit_open(s):
                continue
            for _attempt in range(s.llm_max_retries + 1):
                t0 = time.perf_counter()
                usage = {}
                try:
                    headers = {"Authorization": f"Bearer {provider.key}"} if provider.key else {}
                    async with httpx.AsyncClient(
                        transport=self.transport, timeout=s.llm_timeout_s, trust_env=False
                    ) as client:
                        response = await client.post(
                            provider.api_url + "/chat/completions",
                            headers=headers,
                            json={
                                "model": provider.model,
                                "messages": [instruction, *messages],
                                "response_format": {"type": "json_object"},
                                "temperature": 0,
                                "max_tokens": s.llm_max_tokens,
                                "stream": False,
                            },
                        )
                    response.raise_for_status()
                    if len(response.content) > 256_000:
                        raise ValueError("oversized model response")
                    envelope = response.json()
                    usage = envelope.get("usage") or {}
                    usage = (
                        {k: v for k, v in usage.items() if isinstance(v, int) and 0 <= v <= 10_000_000}
                        if isinstance(usage, dict)
                        else {}
                    )
                    content = envelope["choices"][0]["message"]["content"]
                    value = schema.model_validate_json(content, strict=True)
                    # Plain PII invented/leaked by the model and instruction-shaped output are rejected.
                    if unsafe_output(value.model_dump()):
                        raise ValueError("unsafe model output")
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError, ValidationError):
                    ms = int((time.perf_counter() - t0) * 1000)
                    provider.failures += 1
                    provider.healthy = False
                    provider.opened_at = time.monotonic()
                    provider.calls.append((time.time(), ms))
                    traces.append(
                        trace(
                            "llm",
                            provider.model,
                            task,
                            ms,
                            provider=provider.name,
                            status="failed",
                            prompt_version="m1-v1",
                        )
                    )
                    continue
                ms = int((time.perf_counter() - t0) * 1000)
                provider.failures = 0
                provider.healthy = True
                provider.checked_at = time.monotonic()
                provider.calls.append((time.time(), ms))
                traces.append(
                    trace(
                        "llm",
                        provider.model,
                        task,
                        ms,
                        provider=provider.name,
                        status="ok" if index == 0 and not traces else "fallback",
                        prompt_version="m1-v1",
                        tokens_in=usage.get("prompt_tokens"),
                        tokens_out=usage.get("completion_tokens"),
                    )
                )
                return LLMResult(value, traces, level(provider.name, index))
        return LLMResult(None, traces, "L3")

    async def chat_text(self, messages: list[dict], *, task: str = "chat") -> LLMResult:
        text, traces = "", []
        try:
            async for chunk in self.chat_stream(messages, task=task):
                text += chunk.text
                traces = chunk.traces or traces
        except ModelUnavailable as exc:
            return LLMResult(None, exc.traces, "L3")
        if unsafe_output(text):
            return LLMResult(None, traces, "L3")
        successful = next(t for t in reversed(traces) if t["status"] != "failed")
        index = next(i for i, p in enumerate(self.providers) if p.name == successful["provider"])
        return LLMResult(text, traces, level(successful["provider"], index))

    async def chat_stream(self, messages: list[dict], *, task: str = "chat") -> AsyncIterator[TextChunk]:
        """Real OpenAI-compatible SSE. Failover only before the first text delta.

        A truncated/empty/length-limited stream is NOT successful. No rules fallback.
        Consumers must validate the full answer before exposing untrusted model prose.
        """
        traces = []
        s = self.settings
        if sum(len(m.get("content", "")) for m in messages) > s.llm_max_input_chars:
            raise ModelUnavailable()
        for index, provider in enumerate(self.providers):
            if not provider.available or provider.circuit_open(s):
                continue
            for _attempt in range(s.llm_max_retries + 1):
                t0 = time.perf_counter()
                emitted, stopped, ended, size = False, False, False, 0
                try:
                    headers = {"Authorization": f"Bearer {provider.key}"} if provider.key else {}
                    async with (
                        httpx.AsyncClient(transport=self.transport, timeout=s.llm_timeout_s, trust_env=False) as client,
                        client.stream(
                            "POST",
                            provider.api_url + "/chat/completions",
                            headers=headers,
                            json={
                                "model": provider.model,
                                "messages": messages,
                                "temperature": 0,
                                "max_tokens": s.llm_max_tokens,
                                "stream": True,
                            },
                        ) as response,
                    ):
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if len(line) > 64000:
                                raise ValueError("oversized stream frame")
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                ended = True
                                break
                            envelope = json.loads(data)
                            choices = envelope.get("choices", [])
                            if not choices:
                                if "error" in envelope:
                                    raise ValueError("upstream error")
                                continue  # usage-only frame
                            choice = choices[0]
                            text = choice.get("delta", {}).get("content") or ""
                            if not isinstance(text, str) or (stopped and text):
                                raise ValueError("invalid delta")
                            finish = choice.get("finish_reason")
                            if finish is not None:
                                if finish != "stop":
                                    raise ValueError("incomplete generation")
                                stopped = True
                            size += len(text)
                            if size > s.chat_max_output_chars:
                                raise ValueError("oversized answer")
                            if text:
                                emitted = True
                                yield TextChunk(text=text)
                    if not (emitted and stopped and ended):
                        raise ValueError("truncated or empty stream")
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
                    ms = int((time.perf_counter() - t0) * 1000)
                    provider.failures += 1
                    provider.healthy = False
                    provider.opened_at = time.monotonic()
                    provider.calls.append((time.time(), ms))
                    traces.append(trace("llm", provider.model, task, ms, provider=provider.name, status="failed"))
                    if emitted:
                        raise ModelUnavailable(traces) from None
                    continue
                ms = int((time.perf_counter() - t0) * 1000)
                provider.failures, provider.healthy = 0, True
                provider.checked_at = time.monotonic()
                provider.calls.append((time.time(), ms))
                traces.append(
                    trace(
                        "llm",
                        provider.model,
                        task,
                        ms,
                        provider=provider.name,
                        status="ok" if index == 0 and not traces else "fallback",
                        prompt_version="chat-v1",
                    )
                )
                yield TextChunk(traces=traces, finished=True)
                return
        raise ModelUnavailable(traces)

    async def _probe(self, p: Provider) -> dict:
        if p.available and not p.circuit_open(self.settings) and time.monotonic() - p.checked_at > 15:
            try:
                headers = {"Authorization": f"Bearer {p.key}"} if p.key else {}
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=self.settings.model_probe_timeout_s, trust_env=False
                ) as c:
                    url = p.base_url.rstrip("/") + "/api/tags" if p.name == "ollama" else p.api_url + "/models"
                    r = await c.get(url, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                    names = (
                        [x.get("name") for x in data.get("models", [])]
                        if p.name == "ollama"
                        else [x.get("id") for x in data.get("data", [])]
                    )
                    p.healthy = p.model in names
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                p.healthy = False
            p.checked_at = time.monotonic()
        values = sorted(ms for ts, ms in p.calls if time.time() - ts < 86400)
        return {
            "category": "llm",
            "provider": p.name,
            "model": p.model,
            "deployment": "local" if p.name == "ollama" else "cloud",
            "stage": "字段抽取 / 合规推理",
            "healthy": p.available and p.healthy and not p.circuit_open(self.settings),
            "circuit_open": p.circuit_open(self.settings),
            "p95_latency_ms": values[min(len(values) - 1, int(len(values) * 0.95))] if values else None,
            "calls_24h": len(values),
        }

    async def health(self) -> list[dict]:
        return list(await asyncio.gather(*(self._probe(p) for p in self.providers)))
