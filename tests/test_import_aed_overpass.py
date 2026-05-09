"""Тесты для tools.import_aed_overpass — парсер ответов Overpass и merge."""

from __future__ import annotations

from tools import import_aed_overpass as ovp


def test_parse_overpass_node_with_tags() -> None:
    raw = {
        "elements": [
            {
                "type": "node",
                "lat": 55.7558,
                "lon": 37.6173,
                "tags": {
                    "emergency": "defibrillator",
                    "name": "ТРЦ Красный Кит",
                    "addr:city": "Москва",
                    "indoor": "yes",
                    "opening_hours": "Mo-Su 09:00-22:00",
                },
            },
            {
                "type": "way",
                "center": {"lat": 59.9343, "lon": 30.3351},
                "tags": {"emergency": "defibrillator", "operator": "СПб метрополитен"},
            },
            {"type": "node", "tags": {}},
        ]
    }
    points = ovp.parse_overpass(raw)
    assert len(points) == 2
    moscow = next(p for p in points if p.lat > 55)
    assert moscow.city == "Москва"
    assert "ТРЦ" in moscow.name
    assert "опен" in moscow.note.lower() or "Mo-Su" in moscow.note
    spb = next(p for p in points if p.lon < 31)
    assert spb.name.startswith("СПб")


def test_merge_points_dedups_close_coordinates() -> None:
    existing = [
        {"city": "Москва", "name": "Старая точка", "lat": 55.75500, "lon": 37.61700, "note": "x"},
    ]
    new = [
        # ≤ 4-знака совпадает — дубликат должен быть отброшен.
        ovp.AedPoint(city="Москва", name="OSM-точка", lat=55.7551, lon=37.6171, note="osm"),
        # Совершенно другая точка.
        ovp.AedPoint(city="СПб", name="Pulkovo", lat=59.8, lon=30.26, note="airport"),
    ]
    merged = ovp.merge_points(existing, new)
    assert len(merged) == 2
    cities = {row["city"] for row in merged}
    assert cities == {"Москва", "СПб"}


def test_build_query_contains_bbox_and_tag() -> None:
    q = ovp.build_query((40.0, 19.0, 82.0, 180.0))
    assert "emergency" in q and "defibrillator" in q
    assert "(40.0,19.0,82.0,180.0)" in q
