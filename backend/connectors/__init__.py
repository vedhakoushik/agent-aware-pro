"""Connector registry — the orchestrator asks here for connectors serving a category."""
from __future__ import annotations

from ..schema import Category
from .base import Connector
from .flights import FlightConnector
from .hotels import HotelConnector
from .products import ProductConnector

# Register every connector once. Add a supplier → add it here.
ALL_CONNECTORS: list[Connector] = [
    FlightConnector(),
    HotelConnector(),
    ProductConnector(),
]


def connectors_for(category: Category) -> list[Connector]:
    return [c for c in ALL_CONNECTORS if c.supports(category)]
