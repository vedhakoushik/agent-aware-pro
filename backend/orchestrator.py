"""
Orchestration — deterministic parallel fan-out across the suppliers for a category.

This is the part that used to be a flaky LLM browser agent. Here it's plain, reliable
async: query every relevant connector concurrently, each with its own timeout, capture
timing + status per source, and flatten into one price-sorted, normalized result set.
Each source is cached individually so repeat queries are instant.
"""
from __future__ import annotations

import asyncio
import time

from .cache import cache_get_json, cache_set_json
from .config import settings
from .connectors import connectors_for
from .connectors.base import Connector
from .schema import Intent, Offer, SourceResult


def _cache_key(conn: Connector, intent: Intent) -> str:
    import hashlib
    raw = f"{conn.source}:{intent.category.value}:{sorted(intent.params.items())}"
    return "src:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


async def run_source(conn: Connector, intent: Intent) -> SourceResult:
    """Run one connector with timeout, caching, timing and error capture."""
    key = _cache_key(conn, intent)
    cached = await cache_get_json(key)
    if cached is not None:
        return SourceResult(
            source=conn.source, source_name=conn.source_name, status="ok",
            offers=[Offer(**o) for o in cached], latency_ms=0, live=conn.live,
        )

    t0 = time.monotonic()
    try:
        offers = await asyncio.wait_for(conn.search(intent),
                                        timeout=settings.source_timeout_seconds)
        ms = int((time.monotonic() - t0) * 1000)
        if offers:
            await cache_set_json(key, [o.model_dump() for o in offers])
        return SourceResult(source=conn.source, source_name=conn.source_name,
                            status="ok" if offers else "empty", offers=offers,
                            latency_ms=ms, live=conn.live)
    except asyncio.TimeoutError:
        return SourceResult(source=conn.source, source_name=conn.source_name,
                            status="timeout", latency_ms=int((time.monotonic() - t0) * 1000),
                            live=conn.live, error="Source timed out")
    except Exception as e:
        return SourceResult(source=conn.source, source_name=conn.source_name,
                            status="error", latency_ms=int((time.monotonic() - t0) * 1000),
                            live=conn.live, error=str(e)[:200])


async def gather_sources(intent: Intent) -> list[SourceResult]:
    """Fan out to all connectors for the category, concurrently."""
    conns = connectors_for(intent.category)
    if not conns:
        return []
    return list(await asyncio.gather(*(run_source(c, intent) for c in conns)))


def flatten_offers(sources: list[SourceResult]) -> list[Offer]:
    """One price-sorted list across all sources (offers without a price sort last)."""
    offers = [o for s in sources for o in s.offers]
    return sorted(offers, key=lambda o: o.price.amount if o.price else float("inf"))
