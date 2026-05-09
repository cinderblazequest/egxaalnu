"""Импорт точек АНД из OpenStreetMap (Overpass API).

Запрашивает все объекты с тегом ``emergency=defibrillator`` в указанной
рамке (bounding box) и:
- мерджит их с существующим ``content/aed_locations.json`` (de-dup по
  координатам с точностью 4 знака — это ≈ 11 м на экваторе),
- сохраняет результат с сортировкой по городу/имени.

Запуск (по умолчанию — вся РФ):

    python -m tools.import_aed_overpass

Запуск только по Москве:

    python -m tools.import_aed_overpass --bbox 55.5,37.3,56.0,37.9

Параметры:
    --bbox south,west,north,east   географическая рамка (десятичные градусы)
    --output path                   куда писать (по умолчанию content/aed_locations.json)
    --dry-run                       только распечатать diff, не записывать
    --timeout secs                  тайм-аут запроса к Overpass (по умолчанию 60)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("spas.import_aed")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Россия как bounding box (приближённо — захватывает Калининград и Крым).
DEFAULT_BBOX = (41.0, 19.0, 82.0, 180.0)

USER_AGENT = "spas-ai-bot/0.3 (+https://github.com/cinderblazequest/egxaalnu)"


@dataclasses.dataclass(frozen=True)
class AedPoint:
    city: str
    name: str
    lat: float
    lon: float
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "name": self.name,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "note": self.note,
        }


def build_query(bbox: tuple[float, float, float, float]) -> str:
    """Сгенерировать Overpass-запрос для emergency=defibrillator."""
    south, west, north, east = bbox
    return f"""
[out:json][timeout:60];
(
  node["emergency"="defibrillator"]({south},{west},{north},{east});
  way["emergency"="defibrillator"]({south},{west},{north},{east});
);
out center;
""".strip()


def fetch_overpass(query: str, *, timeout: float = 60.0) -> dict[str, Any]:
    """Отправить запрос в Overpass и вернуть JSON-ответ."""
    data = ("data=" + query).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_overpass(raw: dict[str, Any]) -> list[AedPoint]:
    """Преобразовать ответ Overpass в список ``AedPoint``."""
    elements = raw.get("elements") or []
    points: list[AedPoint] = []
    for el in elements:
        tags = el.get("tags") or {}
        lat = el.get("lat") if "lat" in el else (el.get("center") or {}).get("lat")
        lon = el.get("lon") if "lon" in el else (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        city = (
            tags.get("addr:city")
            or tags.get("addr:town")
            or tags.get("addr:village")
            or tags.get("city")
            or "—"
        )
        name = tags.get("name") or tags.get("operator") or tags.get("description") or "АНД (OSM)"
        note_parts: list[str] = []
        if tags.get("indoor") == "yes":
            note_parts.append("в помещении")
        if tags.get("access"):
            note_parts.append(f"access={tags['access']}")
        if tags.get("opening_hours"):
            note_parts.append(tags["opening_hours"])
        note = "; ".join(note_parts) or "OSM"
        points.append(
            AedPoint(
                city=str(city)[:120],
                name=str(name)[:200],
                lat=float(lat),
                lon=float(lon),
                note=str(note)[:200],
            )
        )
    return points


def merge_points(existing: list[dict[str, Any]], new_points: list[AedPoint]) -> list[dict[str, Any]]:
    """Объединить существующие записи с новыми, де-дуплицируя по округлённым координатам.

    Округление до 3 знаков после запятой даёт точность ≈ 110 м, что разумно
    для АНД (одна точка на здание, а не на каждый этаж).
    """

    def key(d: dict[str, Any]) -> tuple[float, float]:
        return round(float(d["lat"]), 3), round(float(d["lon"]), 3)

    seen: set[tuple[float, float]] = {key(d) for d in existing}
    merged = list(existing)
    for p in new_points:
        k = round(p.lat, 3), round(p.lon, 3)
        if k in seen:
            continue
        seen.add(k)
        merged.append(p.as_dict())
    merged.sort(key=lambda d: (str(d.get("city", "")), str(d.get("name", ""))))
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Импорт АНД из OpenStreetMap.")
    parser.add_argument(
        "--bbox",
        default=",".join(str(v) for v in DEFAULT_BBOX),
        help="south,west,north,east (по умолчанию вся РФ).",
    )
    parser.add_argument(
        "--output",
        default="content/aed_locations.json",
        help="Путь к выходному JSON.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Не писать в файл.")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bbox = tuple(float(v) for v in args.bbox.split(","))
    if len(bbox) != 4:
        log.error("--bbox должен содержать 4 числа через запятую")
        return 2

    query = build_query(bbox)  # type: ignore[arg-type]
    log.info("Запрос Overpass (bbox=%s)…", bbox)
    try:
        raw = fetch_overpass(query, timeout=args.timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        log.error("Overpass недоступен: %s", exc)
        return 3

    new_points = parse_overpass(raw)
    log.info("Получено %d точек из OSM", len(new_points))

    output = Path(args.output)
    if output.exists():
        existing_blob = json.loads(output.read_text(encoding="utf-8"))
        locations = list(existing_blob.get("locations") or [])
    else:
        existing_blob = {"version": "0.3.0", "_comment": "Импортируется из OSM.", "locations": []}
        locations = []

    merged = merge_points(locations, new_points)
    added = len(merged) - len(locations)
    log.info("Добавлено новых точек: %d (всего: %d)", added, len(merged))

    if args.dry_run:
        json.dump(merged[:5], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    existing_blob["locations"] = merged
    output.write_text(
        json.dumps(existing_blob, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log.info("Записано в %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
