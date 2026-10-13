"""Fixed-window rate limiting. Redis-backed so limits hold across API workers;
falls back to in-process counters when no Redis is configured (tests, single-process dev)."""

import time
from collections import defaultdict
from functools import lru_cache

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import get_settings


class RateLimiter:
    def __init__(self, redis: Redis | None) -> None:
        self._redis = redis
        self._local: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))

    async def hit(self, key: str, limit: int, window_s: int = 60) -> None:
        window = int(time.time() // window_s)
        bucket = f"rl:{key}:{window}"
        if self._redis is not None:
            count = await self._redis.incr(bucket)
            if count == 1:
                await self._redis.expire(bucket, window_s)
        else:
            w, c = self._local[key]
            count = c + 1 if w == window else 1
            self._local[key] = (window, count)
        if count > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts. Wait a minute and try again.",
                headers={"Retry-After": str(window_s)},
            )

    def reset(self) -> None:
        self._local.clear()


@lru_cache
def get_rate_limiter() -> RateLimiter:
    url = get_settings().redis_url
    return RateLimiter(Redis.from_url(url) if url else None)
