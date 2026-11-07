"""Live-drill-only HTTP audit guard; no response bodies or credentials are persisted."""

import fcntl
import json
import os
from pathlib import Path

import httpx


class BudgetTransport(httpx.AsyncBaseTransport):
    def __init__(self, counter: Path, label: str, proxy=None):
        self.counter, self.label = counter, label
        self.direct = httpx.AsyncHTTPTransport(retries=0)
        self.cloud = httpx.AsyncHTTPTransport(proxy=proxy, retries=0) if proxy else self.direct

    def record(self, paid):
        with self.counter.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            data = json.loads(handle.read() or '{"model_post_calls":0,"http_counts":{}}')
            if paid and data["model_post_calls"] >= 3:
                raise httpx.ConnectError("drill inference budget exhausted")
            data["model_post_calls"] += int(paid)
            key = self.label + (":alias_POST" if paid else ":health_GET")
            data["http_counts"][key] = data["http_counts"].get(key, 0) + 1
            handle.seek(0)
            handle.truncate()
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())

    async def handle_async_request(self, request):
        cloud = request.url.host == "api.deepseek.com"
        paid = request.method == "POST" and cloud
        if request.method == "POST":
            payload = json.loads(request.content)
            if not paid or payload.get("max_tokens") != 1:
                raise httpx.ConnectError("only bounded cloud health inference allowed", request=request)
        self.record(paid)
        return await (self.cloud if cloud else self.direct).handle_async_request(request)

    async def aclose(self):
        # ProviderChain closes a client per probe; retain pools until process teardown.
        pass
