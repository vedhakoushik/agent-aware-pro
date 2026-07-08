"""
Flight connector — Amadeus Self-Service API, with realistic demo fallback.

LIVE  (AMADEUS_CLIENT_ID/SECRET set): OAuth2 client-credentials → flight-offers-search,
       normalized into canonical Offers.
DEMO  (no keys): generates plausible, varied offers for the route so the whole app —
       comparison, ranking, the grounded recommendation, the UI — works end-to-end with
       zero signup. Swap in keys and the same code path returns real fares.
"""
from __future__ import annotations

import logging
from typing import Any

from urllib.parse import quote

import httpx

from ..config import settings
from ..schema import Category, Intent, Money, Offer
from .base import Connector

logger = logging.getLogger(__name__)

# Minimal city → IATA map (extend as needed). Demo + the Amadeus query both use it.
_IATA = {
    "mumbai": "BOM", "delhi": "DEL", "new delhi": "DEL", "bangalore": "BLR",
    "bengaluru": "BLR", "hyderabad": "HYD", "chennai": "MAA", "kolkata": "CCU",
    "goa": "GOI", "pune": "PNQ", "ahmedabad": "AMD", "jaipur": "JAI", "kochi": "COK",
    "dubai": "DXB", "singapore": "SIN", "london": "LHR", "new york": "JFK",
}

_AIRLINES = [
    ("IndiGo", "6E"), ("Air India", "AI"), ("Vistara", "UK"),
    ("SpiceJet", "SG"), ("Akasa Air", "QP"),
]


def _iata(city: str) -> str:
    return _IATA.get((city or "").strip().lower(), (city or "XXX")[:3].upper())


class FlightConnector(Connector):
    source = "flights"
    source_name = "Google Flights"   # via SerpApi (or Amadeus / demo as fallbacks)
    categories = {Category.flight}

    @property
    def live(self) -> bool:
        # SerpApi's Google Flights engine is the simplest live source (one key, real
        # data) — preferred over Amadeus, which needs an app + OAuth + sparse test data.
        return bool(settings.serpapi_key or (settings.amadeus_client_id and settings.amadeus_client_secret))

    async def search(self, intent: Intent) -> list[Offer]:
        p = intent.params
        origin = _iata(p.get("origin", ""))
        dest = _iata(p.get("destination", ""))
        date = str(p.get("date") or p.get("depart_date") or "") or _default_date()
        if settings.serpapi_key:
            try:
                return await self._serpapi_flights(origin, dest, date)
            except Exception as e:
                logger.warning(f"SerpApi flights failed, trying next: {e}")
        if settings.amadeus_client_id and settings.amadeus_client_secret:
            try:
                return await self._amadeus(origin, dest, date)
            except Exception as e:
                logger.warning(f"Amadeus live call failed, using demo: {e}")
        return self._demo(origin, dest, date, p)

    # ── Live SerpApi Google Flights ──
    async def _serpapi_flights(self, origin: str, dest: str, date: str) -> list[Offer]:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://serpapi.com/search.json", params={
                "engine": "google_flights", "departure_id": origin, "arrival_id": dest,
                "outbound_date": date, "type": 2,  # one-way
                "currency": "INR", "gl": "in", "hl": "en", "api_key": settings.serpapi_key,
            })
            r.raise_for_status()
            data = r.json()
        groups = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        offers: list[Offer] = []
        for i, g in enumerate(groups[:8]):
            segs = g.get("flights", [])
            if not segs:
                continue
            first, last = segs[0], segs[-1]
            offers.append(Offer(
                id=f"serpfl-{i}", source=self.source, source_name="Google Flights",
                category=Category.flight,
                title=f'{first.get("airline","")} {first.get("flight_number","")}'.strip(),
                price=Money(amount=float(g["price"]), currency="INR") if g.get("price") else None,
                # Deep-link straight to the live Google Flights results for THIS route+date
                # (the booking endpoint), not a generic homepage.
                url=("https://www.google.com/travel/flights?q="
                     + quote(f"flights from {origin} to {dest} on {date}")),
                attributes={
                    "airline": first.get("airline", ""),
                    "stops": len(segs) - 1,
                    "duration_minutes": g.get("total_duration"),
                    "depart_time": (first.get("departure_airport", {}).get("time", "") or "")[-5:],
                    "arrive_time": (last.get("arrival_airport", {}).get("time", "") or "")[-5:],
                    "cabin": first.get("travel_class", "Economy"),
                },
            ))
        return offers

    # ── Live Amadeus ──
    async def _amadeus(self, origin: str, dest: str, date: str) -> list[Offer]:
        async with httpx.AsyncClient(timeout=10) as c:
            tok = await c.post(
                "https://test.api.amadeus.com/v1/security/oauth2/token",
                data={"grant_type": "client_credentials",
                      "client_id": settings.amadeus_client_id,
                      "client_secret": settings.amadeus_client_secret},
            )
            tok.raise_for_status()
            token = tok.json()["access_token"]
            r = await c.get(
                "https://test.api.amadeus.com/v2/shopping/flight-offers",
                params={"originLocationCode": origin, "destinationLocationCode": dest,
                        "departureDate": date or "2026-07-01", "adults": 1,
                        "currencyCode": "INR", "max": 8},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = r.json().get("data", [])
        offers: list[Offer] = []
        for i, o in enumerate(data[:8]):
            seg = o["itineraries"][0]["segments"][0]
            dur = o["itineraries"][0]["duration"]  # ISO8601 e.g. PT2H10M
            offers.append(Offer(
                id=f"amadeus-{i}", source=self.source, source_name=self.source_name,
                category=Category.flight,
                title=f'{seg["carrierCode"]}-{seg["number"]}',
                price=Money(amount=float(o["price"]["grandTotal"]),
                            currency=o["price"].get("currency", "INR")),
                attributes={
                    "airline": seg["carrierCode"],
                    "stops": len(o["itineraries"][0]["segments"]) - 1,
                    "duration_minutes": _iso_minutes(dur),
                    "depart_time": seg["departure"]["at"][11:16],
                    "arrive_time": o["itineraries"][0]["segments"][-1]["arrival"]["at"][11:16],
                    "cabin": "Economy",
                },
            ))
        return offers

    # ── Demo data ──
    def _demo(self, origin: str, dest: str, date: str, p: dict[str, Any]) -> list[Offer]:
        # Deterministic-ish spread of fares/times so comparisons are meaningful.
        base = 4200
        rows = [
            (0, 0, 135, "06:10", "Economy", 1.00),
            (1, 0, 130, "09:05", "Economy", 1.18),
            (2, 1, 200, "13:40", "Economy", 0.92),   # cheapest but a stop
            (3, 0, 140, "18:20", "Economy", 1.34),
            (4, 0, 150, "21:55", "Economy", 1.05),
        ]
        offers: list[Offer] = []
        for i, (ai, stops, dur, dep, cabin, mult) in enumerate(rows):
            name, code = _AIRLINES[ai]
            price = round(base * mult / 10) * 10
            arr = _add_minutes(dep, dur)
            offers.append(Offer(
                id=f"demo-fl-{i}", source=self.source, source_name=self.source_name,
                category=Category.flight,
                title=f"{name} {code}-{1000 + i*113 % 8999}",
                price=Money(amount=price, currency="INR"),
                url=f"https://www.google.com/travel/flights?q=flights+{origin}+to+{dest}",
                attributes={"airline": name, "stops": stops, "duration_minutes": dur,
                            "depart_time": dep, "arrive_time": arr, "cabin": cabin},
            ))
        return offers


def _default_date() -> str:
    """Google Flights needs a real future date; default to ~2 weeks out if none given."""
    from datetime import date, timedelta
    return (date.today() + timedelta(days=14)).isoformat()


def _iso_minutes(iso: str) -> int:
    import re
    h = re.search(r"(\d+)H", iso)
    m = re.search(r"(\d+)M", iso)
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


def _add_minutes(hhmm: str, minutes: int) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"
