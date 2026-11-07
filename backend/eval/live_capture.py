"""One-run accounting. Balances stay in memory; only their difference is returned."""

import json
import os
from collections import Counter
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path

import httpx

MODEL_TASK = ContextVar("model_eval_task", default="other")


def atomic_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as file:
        file.write(json.dumps(payload, indent=2) + "\n")
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


async def balance_in_memory(key):
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.get(
                "https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"}
            )
            response.raise_for_status()
            values = response.json()["balance_infos"]
            return {v["currency"]: Decimal(v["total_balance"]) for v in values}
    except Exception:
        raise RuntimeError("balance read failed; details withheld") from None


class CountedModelTransport(httpx.AsyncBaseTransport):
    def __init__(self, budget=40, counter_path=None):
        self.inner = httpx.AsyncHTTPTransport()
        self.budget = budget
        self.counter_path = counter_path
        self.calls = Counter()
        self.statuses = Counter()

    async def handle_async_request(self, request):
        if (
            request.url.host != "api.deepseek.com"
            or request.url.path != "/chat/completions"
            and not request.url.path.endswith("/chat/completions")
        ):
            raise RuntimeError("unexpected model endpoint")
        if sum(self.calls.values()) >= self.budget:
            raise RuntimeError("model request budget exhausted")
        self.calls[MODEL_TASK.get()] += 1
        self.persist_counts()
        response = await self.inner.handle_async_request(request)
        self.statuses[str(response.status_code)] += 1
        self.persist_counts()
        return response

    def persist_counts(self):
        if self.counter_path is not None:
            atomic_json(
                self.counter_path,
                {"model_http_calls_by_task": dict(self.calls), "model_http_status_counts": dict(self.statuses)},
            )

    async def aclose(self):
        # ProviderChain closes each client's transport; the owner closes the shared pool.
        pass

    async def finish(self):
        await self.inner.aclose()
