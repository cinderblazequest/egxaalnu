"""Тесты МЧС RSS (C7): парсинг, regex регионов, доставка."""

from __future__ import annotations

import pytest

from bot.mchs_rss import (
    Alert,
    deliver_alerts,
    known_regions,
    map_to_scenario,
    match_region,
    parse_rss,
    render_alert,
)
from bot.storage import Storage

SAMPLE_RSS = """<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'>
<channel>
  <title>МЧС</title>
  <item>
    <title>В Москве объявлено штормовое предупреждение</title>
    <link>https://example.com/1</link>
    <guid>1-moscow-storm</guid>
    <description>Сильный ветер и ливень в Москве. Берегите себя.</description>
    <category>ураган</category>
  </item>
  <item>
    <title>Пожар в Санкт-Петербурге</title>
    <link>https://example.com/2</link>
    <guid>2-spb-fire</guid>
    <description>Возгорание в Санкт-Петербурге, эвакуация.</description>
    <category>пожар</category>
  </item>
  <item>
    <title>Штатная новость без региона</title>
    <link>https://example.com/3</link>
    <guid>3-misc</guid>
    <description>Сводка за неделю.</description>
    <category>информация</category>
  </item>
</channel>
</rss>
""".encode()


def test_parse_rss_returns_three_alerts() -> None:
    alerts = parse_rss(SAMPLE_RSS)
    assert len(alerts) == 3
    assert alerts[0].title.startswith("В Москве")
    assert alerts[0].guid == "1-moscow-storm"
    assert "Москве" in alerts[0].description


def test_parse_rss_invalid_returns_empty() -> None:
    assert parse_rss(b"not xml") == []


def test_match_region_keywords() -> None:
    a = parse_rss(SAMPLE_RSS)[0]
    assert match_region(a, "moscow")
    assert not match_region(a, "spb")
    assert match_region(a, "all")


def test_map_to_scenario_from_category() -> None:
    a = parse_rss(SAMPLE_RSS)[1]
    assert map_to_scenario(a) == "ozhog"


def test_known_regions_includes_all() -> None:
    regs = known_regions()
    assert "moscow" in regs
    assert "all" in regs


def test_render_alert_includes_scenario_link() -> None:
    a = Alert(
        guid="g",
        title="Test",
        link="https://example.com/x",
        description="desc",
        category="пожар",
    )
    body = render_alert(a, scenario="ozhog")
    assert "ozhog" in body
    assert "Test" in body


@pytest.mark.asyncio
async def test_deliver_alerts_dedupes_via_seen(tmp_path) -> None:
    storage = Storage(str(tmp_path / "rss.db"))
    await storage.init()
    try:
        await storage.add_alert_subscription(7, "moscow")
        sent: list[tuple[int, str]] = []

        async def send(uid: int, text: str) -> None:
            sent.append((uid, text))

        alerts = parse_rss(SAMPLE_RSS)
        await deliver_alerts(storage, alerts, send=send)
        first_count = len(sent)
        assert first_count >= 1, "expected at least one delivery for Moscow user"

        # Second pass: all alerts already seen → no duplicate sends.
        await deliver_alerts(storage, alerts, send=send)
        assert len(sent) == first_count
    finally:
        await storage.close()
