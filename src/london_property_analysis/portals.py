from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Listing:
    source: str
    source_id: str
    url: str
    captured_at: datetime
    price: int | None
    address: str | None
    postcode: str | None
    bedrooms: int | None
    bathrooms: int | None
    property_type: str | None
    tenure: str | None
    agent: str | None


class ListingCollector(Protocol):
    """Collector boundary for authorised listing sources."""

    source: str

    def collect(self, query: str, limit: int = 100) -> list[Listing]:
        ...


class AuthorisationRequiredCollector:
    source = "portal"

    def collect(self, query: str, limit: int = 100) -> list[Listing]:
        raise PermissionError(
            "Use this collector only with a licensed API, written permission, "
            "or user-provided exports/HTML that you are allowed to process."
        )

