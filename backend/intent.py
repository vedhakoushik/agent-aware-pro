"""
Intent understanding — natural language → structured Intent.

Primary: the LLM classifies the category and extracts normalized params (this is a
real, valuable LLM job — understanding, not data fetching). Fallback: a fast heuristic
so the app still works when no LLM is configured or the call fails.
"""
from __future__ import annotations

import re

from .llm import complete_json
from .schema import Category, Intent

_SYSTEM = """You convert a travel/shopping search into structured JSON. Categories:
flight, hotel, product, train, general.
Return JSON: {"category": "...", "params": {...}}.
- flight/train: params origin, destination, date (YYYY-MM-DD if given), cabin_class (optional).
- hotel: params location, check_in, check_out, guests (optional).
- product: params product_name, brand (optional), condition (optional).
Only include params you can actually read from the query. Do not invent values.
If the query is too vague to search, add "clarification": "<one short question>"."""


async def parse_intent(query: str) -> Intent:
    data = await complete_json(_SYSTEM, query, max_tokens=400)
    if data and data.get("category"):
        try:
            return Intent(
                category=Category(str(data["category"]).lower()),
                raw_query=query,
                params={k: v for k, v in (data.get("params") or {}).items() if v not in (None, "")},
                clarification=data.get("clarification"),
            )
        except ValueError:
            pass
    return _heuristic(query)


def _heuristic(query: str) -> Intent:
    q = query.lower()
    if any(w in q for w in ("flight", "fly", "flights")):
        cat, params = Category.flight, _route(q)
    elif any(w in q for w in ("train", "rail")):
        cat, params = Category.train, _route(q)
    elif any(w in q for w in ("hotel", "stay", "resort", "room")):
        cat = Category.hotel
        m = re.search(r"in ([a-z ]+)", q)
        params = {"location": m.group(1).strip()} if m else {}
    else:
        cat, params = Category.product, {"product_name": query.strip()}
    return Intent(category=cat, raw_query=query, params=params)


def _route(q: str) -> dict:
    m = re.search(r"(?:from )?([a-z ]+?) to ([a-z ]+?)(?:\s|$|on|under|this|next)", q)
    if m:
        return {"origin": m.group(1).strip(), "destination": m.group(2).strip()}
    return {}
