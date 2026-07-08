"""
Product connector — SerpApi Google Shopping (structured JSON), with demo fallback.

LIVE (SERPAPI_KEY set): real live prices/ratings/sellers across Amazon, Flipkart,
     Walmart, etc. as structured JSON — no scraping, no bot walls.
DEMO (no key): plausible product offers so the app works end-to-end immediately.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..schema import Category, Intent, Money, Offer
from .base import Connector

logger = logging.getLogger(__name__)


class ProductConnector(Connector):
    source = "serpapi"
    source_name = "Google Shopping"
    categories = {Category.product}

    @property
    def live(self) -> bool:
        return bool(settings.serpapi_key)

    async def search(self, intent: Intent) -> list[Offer]:
        q = str(intent.params.get("product_name") or intent.raw_query or "").strip()
        if self.live:
            try:
                return await self._serpapi(q)
            except Exception as e:
                logger.warning(f"SerpApi live call failed, using demo: {e}")
        return self._demo(q)

    async def _serpapi(self, q: str) -> list[Offer]:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://serpapi.com/search.json", params={
                "engine": "google_shopping", "q": q, "gl": "in", "hl": "en",
                "api_key": settings.serpapi_key,
            })
            r.raise_for_status()
            items = r.json().get("shopping_results", [])
        offers: list[Offer] = []
        for i, it in enumerate(items[:8]):
            price = it.get("extracted_price")
            offers.append(Offer(
                id=f"serp-{i}", source=self.source, source_name=it.get("source", "Shopping"),
                category=Category.product, title=it.get("title", "")[:90],
                price=Money(amount=float(price), currency="INR") if price else None,
                url=it.get("product_link") or it.get("link"),
                attributes={"seller": it.get("source", ""), "rating": it.get("rating"),
                            "reviews": it.get("reviews"), "delivery": it.get("delivery", "")},
            ))
        return offers

    def _demo(self, q: str) -> list[Offer]:
        title = q.title() or "Product"
        rows = [
            ("Flipkart", 65999, 4.5, 1820, "Free delivery"),
            ("Amazon", 67499, 4.6, 9410, "Delivery in 2 days"),
            ("Croma", 64990, 4.3, 540, "Store pickup"),
            ("Reliance Digital", 66990, 4.4, 310, "Free delivery"),
        ]
        return [
            Offer(id=f"demo-pr-{i}", source=self.source, source_name=seller,
                  category=Category.product, title=f"{title} (128GB)",
                  price=Money(amount=price, currency="INR"),
                  url=f"https://www.google.com/search?q={q}+{seller}",
                  attributes={"seller": seller, "rating": rating, "reviews": reviews,
                              "delivery": delivery})
            for i, (seller, price, rating, reviews, delivery) in enumerate(rows)
        ]
