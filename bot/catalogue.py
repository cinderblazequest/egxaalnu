"""Загрузчик базы сценариев первой помощи."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("spas.scenarios")


@dataclass
class TestQuestion:
    q: str
    options: list[str]
    correct: int


@dataclass
class Scenario:
    id: str
    title: str
    icon: str
    category: str
    summary: str
    steps: list[str]
    metronome: bool
    phone: str
    post_test: list[TestQuestion]
    pre_test: list[TestQuestion]


@dataclass
class AedLocation:
    city: str
    name: str
    lat: float
    lon: float
    note: str = ""


class Catalogue:
    def __init__(self, content_dir: Path) -> None:
        scenarios_path = content_dir / "scenarios.json"
        aed_path = content_dir / "aed_locations.json"

        scenarios_blob = json.loads(scenarios_path.read_text(encoding="utf-8"))
        aed_blob = json.loads(aed_path.read_text(encoding="utf-8"))

        self.scenarios: dict[str, Scenario] = {}
        for raw in scenarios_blob["scenarios"]:
            scenario = Scenario(
                id=raw["id"],
                title=raw["title"],
                icon=raw.get("icon", "•"),
                category=raw.get("category", "minor"),
                summary=raw.get("summary", ""),
                steps=[step["text"] for step in raw["steps"]],
                metronome=bool(raw.get("metronome")),
                phone=raw.get("phone", "112"),
                post_test=[TestQuestion(**q) for q in raw.get("post_test", [])],
                pre_test=[TestQuestion(**q) for q in raw.get("pre_test", [])],
            )
            self.scenarios[scenario.id] = scenario

        self.aed: list[AedLocation] = [AedLocation(**raw) for raw in aed_blob["locations"]]
        log.info("Загружено: %d сценариев, %d точек АНД", len(self.scenarios), len(self.aed))

    def list_critical(self) -> list[Scenario]:
        return [s for s in self.scenarios.values() if s.category == "critical"]

    def list_urgent(self) -> list[Scenario]:
        return [s for s in self.scenarios.values() if s.category == "urgent"]

    def list_minor(self) -> list[Scenario]:
        return [s for s in self.scenarios.values() if s.category == "minor"]
