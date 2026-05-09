"""
Поиск ближайшей точки АНД (автоматического наружного дефибриллятора)
по геолокации пользователя.

Используется простой плоско-сферный расчёт расстояния (haversine) — для
расстояний < 200 км достаточно точно. В будущем планируется интеграция
Overpass API (OpenStreetMap, тег emergency=defibrillator) и краудсорс
от пользователей бота.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bot.catalogue import AedLocation


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@dataclass
class AedHit:
    location: AedLocation
    distance_km: float


def nearest(lat: float, lon: float, locations: list[AedLocation], k: int = 3) -> list[AedHit]:
    hits = [AedHit(location=loc, distance_km=haversine_km(lat, lon, loc.lat, loc.lon)) for loc in locations]
    hits.sort(key=lambda h: h.distance_km)
    return hits[:k]
