"""
Hotel connector — demo data (wire a real provider, e.g. a RapidAPI hotel API, the same
way the flight/product connectors integrate Amadeus/SerpApi).
"""
from __future__ import annotations

from ..schema import Category, Intent, Money, Offer
from .base import Connector


class HotelConnector(Connector):
    source = "hotels"
    source_name = "Hotels"
    categories = {Category.hotel}

    @property
    def live(self) -> bool:
        return False

    async def search(self, intent: Intent) -> list[Offer]:
        loc = str(intent.params.get("location") or intent.params.get("destination") or "the city").title()
        rows = [
            ("Booking.com", "The Grand Retreat", 4200, 4.6, "Deluxe Room", ["Free WiFi", "Breakfast", "Pool"]),
            ("Agoda", "City Comfort Inn", 2890, 4.2, "Standard Room", ["Free WiFi", "Parking"]),
            ("MakeMyTrip", "Hilltop Resort & Spa", 6100, 4.7, "Suite", ["WiFi", "Breakfast", "Spa", "Pool"]),
            ("OYO", "Cozy Stay", 1750, 3.9, "Standard Room", ["Free WiFi"]),
        ]
        return [
            Offer(id=f"demo-ho-{i}", source=self.source, source_name=site,
                  category=Category.hotel, title=name,
                  price=Money(amount=price, currency="INR"),
                  url=f"https://www.google.com/search?q={name}+{loc}",
                  attributes={"rating": rating, "room_type": room, "area": loc,
                              "amenities": amen, "price_per_night": price})
            for i, (site, name, price, rating, room, amen) in enumerate(rows)
        ]
