"""Тесты функций поиска ближайших АНД."""

from __future__ import annotations

from bot.aed import nearest
from bot.catalogue import AedLocation


def _moscow_red_square() -> tuple[float, float]:
    return 55.7539, 37.6208


def test_nearest_returns_sorted_results() -> None:
    locations = [
        AedLocation(city="A", name="A1", lat=55.0, lon=37.0, note=""),
        AedLocation(city="A", name="A2", lat=55.7, lon=37.6, note=""),
        AedLocation(city="A", name="A3", lat=60.0, lon=30.0, note=""),
    ]
    lat, lon = _moscow_red_square()
    hits = nearest(lat, lon, locations, k=3)
    assert len(hits) == 3
    assert hits[0].location.name == "A2"
    assert hits[0].distance_km < hits[1].distance_km < hits[2].distance_km


def test_nearest_k_limits_results() -> None:
    locations = [
        AedLocation(city="A", name=str(i), lat=55.0 + i * 0.01, lon=37.0, note="") for i in range(10)
    ]
    hits = nearest(55.0, 37.0, locations, k=3)
    assert len(hits) == 3


def test_nearest_handles_empty() -> None:
    hits = nearest(55.0, 37.0, [], k=3)
    assert hits == []
