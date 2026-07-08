"""
Connector interface — every supplier implements this one contract.

A connector turns an `Intent` into a list of normalized `Offer`s. It declares which
categories it serves and whether it's running on LIVE data (real API keys present) or
realistic DEMO data. The orchestrator handles timing, timeouts and error capture, so a
connector just focuses on "fetch + normalize".
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..schema import Category, Intent, Offer


class Connector(ABC):
    source: str = "base"
    source_name: str = "Base"
    categories: set[Category] = set()

    @property
    def live(self) -> bool:
        """True when configured against a real API; False = demo data."""
        return False

    def supports(self, category: Category) -> bool:
        return category in self.categories

    @abstractmethod
    async def search(self, intent: Intent) -> list[Offer]:
        ...
