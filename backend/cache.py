"""
Cache layer — repeat searches return instantly instead of re-hitting suppliers.

Uses Redis when REDIS_URL is set; otherwise a process-local TTL dict so the app works
with zero infra. Supplier responses are cached per (category, params) for a short TTL —
the single biggest reason real metasearch feels fast.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from .config import settings


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if not item:
            return None
        expires, val = item
        if expires < time.monotonic():
            self._store.pop(key, None)
            return None
        return val

    async def set(self, key: str, val: str, ttl: int) -> None:
        self._store[key] = (time.monotonic() + ttl, val)


class _RedisCache:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis
        self._r = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        try:
            return await self._r.get(key)
        except Exception:
            return None

    async def set(self, key: str, val: str, ttl: int) -> None:
        try:
            await self._r.set(key, val, ex=ttl)
        except Exception:
            pass


def _build():
    if settings.redis_url:
        try:
            return _RedisCache(settings.redis_url)
        except Exception:
            pass
    return _MemoryCache()


_cache = _build()


async def cache_get_json(key: str) -> Optional[Any]:
    raw = await _cache.get(key)
    return json.loads(raw) if raw else None


async def cache_set_json(key: str, value: Any, ttl: Optional[int] = None) -> None:
    await _cache.set(key, json.dumps(value), ttl or settings.cache_ttl_seconds)
