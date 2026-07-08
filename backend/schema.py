"""
Canonical schema — the single shape every supplier is normalized into.

This is the heart of the professional design: each connector translates its provider's
bespoke response into these models, so everything downstream (ranking, the UI, the LLM
reasoning) speaks ONE language and never sees a provider's raw quirks. Add a new
supplier → write one connector that emits `Offer`s → the rest of the app just works.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    flight = "flight"
    hotel = "hotel"
    product = "product"
    train = "train"
    general = "general"


class Money(BaseModel):
    amount: float
    currency: str = "INR"

    def __str__(self) -> str:
        sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(self.currency, "")
        return f"{sym}{self.amount:,.0f}"


class Intent(BaseModel):
    """Structured understanding of the user's natural-language query."""
    category: Category = Category.general
    raw_query: str = ""
    # Normalized params — origin/destination/date for travel, product_name for shopping, etc.
    params: dict[str, Any] = Field(default_factory=dict)
    clarification: Optional[str] = None   # set when the query is too vague to act on


class Offer(BaseModel):
    """One normalized, comparable option from one supplier."""
    id: str                              # stable within a response; what the LLM cites
    source: str                          # connector / supplier id, e.g. "amadeus"
    source_name: str = ""                # human label, e.g. "Amadeus"
    category: Category = Category.general
    title: str
    price: Optional[Money] = None
    url: Optional[str] = None
    # Category-specific comparable fields, already normalized
    # (flight: airline, duration_minutes, stops, cabin, depart_time, arrive_time;
    #  product: brand, rating, seller, in_stock; hotel: rating, area, room_type…)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SourceResult(BaseModel):
    """What one supplier returned, with health/timing for diagnostics."""
    source: str
    source_name: str
    status: str = "ok"                   # ok | empty | error | timeout
    offers: list[Offer] = Field(default_factory=list)
    latency_ms: int = 0
    live: bool = False                   # True = real API, False = demo data
    error: Optional[str] = None


class Recommendation(BaseModel):
    """A GROUNDED recommendation — winner_id MUST reference a real offer in the set."""
    winner_id: Optional[str] = None
    headline: str = ""
    reasoning: str = ""
    trade_offs: list[str] = Field(default_factory=list)
    confidence: str = "medium"           # high | medium | low


class SearchResponse(BaseModel):
    query: str
    intent: Intent
    sources: list[SourceResult] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)   # flattened, price-sorted
    recommendation: Optional[Recommendation] = None
    total_ms: int = 0
    stats: dict[str, Any] = Field(default_factory=dict)
