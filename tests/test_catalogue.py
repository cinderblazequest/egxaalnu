"""Тесты загрузчика контента сценариев."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.catalogue import Catalogue

CONTENT = Path(__file__).resolve().parents[1] / "content"


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return Catalogue(CONTENT)


def test_30_scenarios(catalogue: Catalogue) -> None:
    assert len(catalogue.scenarios) >= 30, "должно быть минимум 30 сценариев"


def test_categories_split(catalogue: Catalogue) -> None:
    crit = catalogue.list_critical()
    urg = catalogue.list_urgent()
    minor = catalogue.list_minor()
    total = len(crit) + len(urg) + len(minor)
    assert total == len(catalogue.scenarios)
    assert crit, "должны быть критические сценарии"
    assert urg, "должны быть срочные сценарии"


def test_each_scenario_has_pre_and_post(catalogue: Catalogue) -> None:
    for s in catalogue.scenarios.values():
        assert s.pre_test, f"{s.id}: должен быть хотя бы 1 pre-вопрос"
        assert s.post_test, f"{s.id}: должен быть хотя бы 1 post-вопрос"
        for q in (*s.pre_test, *s.post_test):
            assert 0 <= q.correct < len(q.options)
            assert len(q.options) >= 2


def test_phone_is_emergency(catalogue: Catalogue) -> None:
    for s in catalogue.scenarios.values():
        assert s.phone in {"112", "103"}, f"{s.id} имеет телефон {s.phone}"


def test_aed_locations_populated(catalogue: Catalogue) -> None:
    assert len(catalogue.aed) >= 25
    cities = {loc.city for loc in catalogue.aed}
    assert len(cities) >= 8, f"должно быть >=8 городов, нашёл {len(cities)}: {cities}"
    for loc in catalogue.aed:
        assert -90 <= loc.lat <= 90
        assert -180 <= loc.lon <= 180
        assert loc.name
