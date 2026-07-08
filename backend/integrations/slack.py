"""
Slack integration (read-only) — async port for the FastAPI service.

Lists the workspace's channels and reads recent messages via the Slack Web API using
SLACK_BOT_TOKEN. Strictly read-only: never posts/edits/deletes. Short TTL cache so page
renders don't hammer Slack's rate limits.
"""
from __future__ import annotations

import logging
import time

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_API = "https://slack.com/api"
_cache: dict[str, tuple[float, object]] = {}


def is_configured() -> bool:
    t = settings.slack_bot_token.strip()
    return bool(t) and t.startswith("xoxb-")


def _cached(key: str):
    hit = _cache.get(key)
    return hit[1] if hit and hit[0] > time.monotonic() else None


def _store(key: str, val, ttl: float):
    _cache[key] = (time.monotonic() + ttl, val)


async def _call(method: str, params: dict | None = None) -> dict:
    token = settings.slack_bot_token.strip()
    if not token:
        return {"ok": False, "error": "not_configured"}
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(f"{_API}/{method}",
                            headers={"Authorization": f"Bearer {token}"},
                            params=params or {})
        data = r.json()
        if not data.get("ok"):
            logger.warning(f"Slack {method}: {data.get('error')}")
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auth_test() -> dict:
    if (c := _cached("auth")) is not None:
        return c
    d = await _call("auth.test")
    out = {"ok": bool(d.get("ok")), "team": d.get("team", ""), "user": d.get("user", ""),
           "url": d.get("url", ""), "error": d.get("error", "")}
    if out["ok"]:
        _store("auth", out, 600)
    return out


async def list_channels(limit: int = 200) -> dict:
    if (c := _cached("channels")) is not None:
        return c
    d = await _call("conversations.list", {"types": "public_channel,private_channel",
                                           "exclude_archived": "true", "limit": limit})
    if not d.get("ok"):
        return {"ok": False, "channels": [], "error": d.get("error", "unknown")}
    chans = sorted([{
        "id": c.get("id"), "name": c.get("name", ""),
        "is_private": bool(c.get("is_private")), "is_member": bool(c.get("is_member")),
        "num_members": c.get("num_members", 0),
        "topic": (c.get("topic") or {}).get("value", ""),
    } for c in d.get("channels", [])], key=lambda x: x["name"].lower())
    out = {"ok": True, "channels": chans, "error": ""}
    _store("channels", out, 120)
    return out


async def _user_map() -> dict:
    if (c := _cached("users")) is not None:
        return c
    d = await _call("users.list", {"limit": 500})
    umap = {}
    if d.get("ok"):
        for u in d.get("members", []):
            p = u.get("profile", {}) or {}
            umap[u.get("id")] = p.get("display_name") or p.get("real_name") or u.get("name") or u.get("id")
    _store("users", umap, 600)
    return umap


async def get_messages(channel_id: str, limit: int = 15) -> dict:
    key = f"msgs:{channel_id}:{limit}"
    if (c := _cached(key)) is not None:
        return c
    d = await _call("conversations.history", {"channel": channel_id, "limit": limit})
    if not d.get("ok"):
        return {"ok": False, "messages": [], "error": d.get("error", "unknown")}
    umap = await _user_map()
    msgs = [{"author": umap.get(m.get("user", ""), m.get("username", "") or "Unknown"),
             "text": m.get("text", ""), "ts": m.get("ts", "")}
            for m in reversed(d.get("messages", []))
            if m.get("subtype") not in ("channel_join", "channel_leave")]
    out = {"ok": True, "messages": msgs, "error": ""}
    _store(key, out, 20)
    return out
