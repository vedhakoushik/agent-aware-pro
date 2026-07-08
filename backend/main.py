"""
API service — FastAPI. Decoupled from the UI; everything is JSON over HTTP.

Endpoints:
  GET  /api/health           — liveness + which providers are live vs demo
  POST /api/search           — full search (intent → fan-out → grounded recommendation)
  GET  /api/search/stream    — same, but SSE: streams intent, then each source as it
                               returns, then the recommendation (the "results pour in" UX)
  GET  /                     — serves the frontend
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .connectors import ALL_CONNECTORS, connectors_for
from .integrations import slack
from .intent import parse_intent
from .orchestrator import flatten_offers, gather_sources, run_source
from .reasoning import recommend
from .schema import Intent, SearchResponse

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Agent-Aware Pro", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class SearchBody(BaseModel):
    query: str


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "sources": [{"source": c.source, "name": c.source_name,
                     "categories": [x.value for x in c.categories],
                     "mode": "live" if c.live else "demo"} for c in ALL_CONNECTORS],
    }


@app.post("/api/search", response_model=SearchResponse)
async def search(body: SearchBody) -> SearchResponse:
    t0 = time.monotonic()
    intent = await parse_intent(body.query)
    if intent.clarification:
        return SearchResponse(query=body.query, intent=intent,
                              total_ms=int((time.monotonic() - t0) * 1000))
    sources = await gather_sources(intent)
    offers = flatten_offers(sources)
    rec = await recommend(intent, offers)
    return SearchResponse(
        query=body.query, intent=intent, sources=sources, offers=offers,
        recommendation=rec, total_ms=int((time.monotonic() - t0) * 1000),
        stats={"sources": len(sources),
               "sources_with_results": sum(1 for s in sources if s.offers),
               "offers": len(offers)},
    )


@app.get("/api/search/stream")
async def search_stream(q: str):
    """Server-Sent Events: intent → each source as it finishes → recommendation → done."""
    async def gen():
        t0 = time.monotonic()
        intent = await parse_intent(q)
        yield {"event": "intent", "data": intent.model_dump_json()}
        if intent.clarification:
            yield {"event": "done", "data": json.dumps({"total_ms": 0})}
            return

        conns = connectors_for(intent.category)
        all_offers = []
        # Stream each source the moment it returns, rather than waiting for the slowest.
        tasks = [asyncio.create_task(run_source(c, intent)) for c in conns]
        for fut in asyncio.as_completed(tasks):
            res = await fut
            all_offers.extend(res.offers)
            yield {"event": "source", "data": res.model_dump_json()}

        offers = sorted(all_offers, key=lambda o: o.price.amount if o.price else float("inf"))
        rec = await recommend(intent, offers)
        yield {"event": "recommendation",
               "data": json.dumps({"recommendation": rec.model_dump() if rec else None,
                                   "offers": [o.model_dump() for o in offers]}, default=str)}
        yield {"event": "done", "data": json.dumps({"total_ms": int((time.monotonic() - t0) * 1000)})}

    return EventSourceResponse(gen())


# ── Source retry — the API-appropriate "recovery" action ──
# (No browser agent: with structured APIs a source either works or returns a clean
#  status. "Recovery" = re-run one source, optionally with a refined query.)
class RetryBody(BaseModel):
    source: str
    query: str


@app.post("/api/source/retry")
async def source_retry(body: RetryBody):
    intent = await parse_intent(body.query)
    conn = next((c for c in ALL_CONNECTORS if c.source == body.source), None)
    if not conn:
        return {"error": f"unknown source '{body.source}'"}
    res = await run_source(conn, intent)
    return res.model_dump()


# ── Slack (read-only channel viewer) ──
@app.get("/api/slack/status")
async def slack_status():
    if not slack.is_configured():
        return {"configured": False}
    return {"configured": True, **(await slack.auth_test())}


@app.get("/api/slack/channels")
async def slack_channels():
    return await slack.list_channels()


@app.get("/api/slack/messages")
async def slack_messages(channel: str, limit: int = 15):
    return await slack.get_messages(channel, limit)


# ── Frontend (served by the same process for zero-config local run) ──
if (_FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND / "assets"), name="assets")


@app.get("/")
async def index():
    return FileResponse(_FRONTEND / "index.html")
