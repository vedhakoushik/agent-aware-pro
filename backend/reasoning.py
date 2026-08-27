"""
Recommendation — the LLM reasons over STRUCTURED offers and explains a pick.

Crucially GROUNDED: the model is given the real offers and must return one of their ids.
We validate the id against the actual set, so it can never invent a flight/price. If the
LLM is unavailable or returns a bad id, we fall back to a deterministic cheapest pick with
a templated, still-truthful explanation. Zero offers → no recommendation, stated honestly.
"""
from __future__ import annotations

import json

from .llm import complete_json
from .schema import Intent, Offer, Recommendation
from .security.redact import wrap_untrusted, detect_injection, redact_pii

_SYSTEM = """You are a sharp, honest comparison advisor. You are given a JSON list of
real offers (each with an id, price and attributes) for the user's search. Pick the best
overall VALUE and explain why with specific trade-offs against the alternatives.

Rules:
- "winner_id" MUST be one of the provided offer ids. Never invent an option or a number.
- Cite real figures from the data (prices, durations, ratings).
- Be honest: if the cheapest sacrifices something (a stop, lower rating), say so.
Return JSON: {"winner_id","headline","reasoning","trade_offs":["..."],"confidence":"high|medium|low"}"""


def _compact(offers: list[Offer]) -> str:
    # title/attributes come from supplier data — anyone who can list an offer (a hotel
    # owner, a seller) controls this free text. Redact PII before it goes anywhere near
    # a prompt or gets echoed back through the API.
    return json.dumps([
        {"id": o.id, "source": o.source_name, "title": redact_pii(o.title)[0],
         "price": o.price.amount if o.price else None,
         **{k: (redact_pii(v)[0] if isinstance(v, str) else v)
            for k, v in o.attributes.items() if v not in (None, "")}}
        for o in offers[:12]
    ], default=str)


async def recommend(intent: Intent, offers: list[Offer]) -> Recommendation | None:
    if not offers:
        return None

    valid_ids = {o.id for o in offers}
    # Offer titles/attributes are untrusted (supplier-listed free text) — fence them so
    # the model treats them as data, not instructions. This is defense-in-depth: the
    # REAL backstop is the winner_id membership check below, which can't be bypassed by
    # any prompt content because it validates against the actual offer set, not the
    # LLM's claim.
    user = (f'Search: "{intent.raw_query}" (category: {intent.category.value})\n'
            f"Offers:\n{wrap_untrusted(_compact(offers), source='supplier offer data')}")
    data = await complete_json(_SYSTEM, user, max_tokens=700)

    if data and data.get("winner_id") in valid_ids:
        text_fields = " ".join(str(data.get(f, "")) for f in ("headline", "reasoning")) \
            + " ".join(str(t) for t in (data.get("trade_offs") or []))
        injected = detect_injection(text_fields)
        if not injected:
            return Recommendation(
                winner_id=data["winner_id"],
                headline=str(data.get("headline", ""))[:160],
                reasoning=str(data.get("reasoning", ""))[:600],
                trade_offs=[str(t)[:160] for t in (data.get("trade_offs") or [])][:4],
                confidence=str(data.get("confidence", "medium")).lower(),
            )
        # The LLM's own output text carries injection-shaped phrasing — something got
        # through the fence. Don't show it to the user; fall through to the
        # deterministic pick below instead of trusting a possibly-steered explanation.

    # Deterministic fallback — cheapest priced offer, truthful templated explanation.
    priced = [o for o in offers if o.price]
    best = min(priced, key=lambda o: o.price.amount) if priced else offers[0]
    others = [o for o in priced if o.id != best.id]
    headline = f"{best.source_name} — {best.title}"
    reasoning = f"Lowest price found at {str(best.price)}." if best.price else "Top available option."
    if others:
        nxt = min(others, key=lambda o: o.price.amount)
        diff = int(nxt.price.amount - best.price.amount) if best.price else 0
        if diff > 0:
            reasoning += f" That's ₹{diff:,} less than the next option ({nxt.source_name})."
    return Recommendation(winner_id=best.id, headline=headline, reasoning=reasoning,
                          trade_offs=[], confidence="medium")
