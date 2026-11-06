"""Redis 滑动窗口限流（有序集合）。"""

from __future__ import annotations

import secrets
import time

from redis.asyncio import Redis


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def hit(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
        """记录一次请求；返回 (是否放行, 建议重试秒数)。"""
        now = time.time()
        k = f"rl:{key}"
        async with self.redis.pipeline(transaction=True) as p:
            p.zremrangebyscore(k, 0, now - window_s)
            p.zadd(k, {f"{now}:{secrets.token_hex(4)}": now})
            p.zcard(k)
            p.zrange(k, 0, 0, withscores=True)
            p.zremrangebyrank(k, limit, -1)  # Denied attempts never grow the bucket without bound.
            p.expire(k, window_s)
            _, _, count, oldest, _, _ = await p.execute()
        if count > limit:
            retry = int(window_s - (now - oldest[0][1])) + 1 if oldest else window_s
            return False, max(retry, 1)
        return True, 0
