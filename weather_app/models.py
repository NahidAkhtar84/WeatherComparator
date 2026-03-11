from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Location:
    city: str
    latitude: float
    longitude: float
