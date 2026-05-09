"""МЧС RSS push (C7).

Опрашивает публичный RSS МЧС или резервный JSON-источник, фильтрует
новости по слову региона, мапит на сценарий первой помощи и шлёт пушу
подписчикам команды ``/subscribe_alerts``.

Запускается фоновой задачей из ``bot/__main__.py`` если выставлена
переменная окружения ``MCHS_RSS_ENABLED=1``. По умолчанию выключено,
чтобы CI/тесты не лезли в сеть.

Парсинг — через ``xml.etree.ElementTree`` (без внешней зависимости),
устойчив к отсутствию некоторых полей.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import aiohttp

from bot.storage import Storage

AsyncSender = Callable[[int, str], Awaitable[None]]

log = logging.getLogger("spas.mchs_rss")

_DEFAULT_URL = "https://www.mchs.gov.ru/news/rss"

# region (lowercase) -> [keywords] heuristic. Совпадение по любому ключевому слову
# в title/description новости.
_REGION_MATCHERS: dict[str, tuple[str, ...]] = {
    "moscow": ("москв", "москов"),
    "spb": ("санкт-петер", "петербург", "ленингр"),
    "novosibirsk": ("новосиб",),
    "krasnodar": ("краснодар", "кубан"),
    "ekaterinburg": ("екатеринб", "свердлов"),
    "kazan": ("казан", "татарст"),
    "rostov": ("ростов",),
    "samara": ("самар",),
    "ufa": ("уфа", "башкорт"),
    "perm": ("перм",),
    "voronezh": ("воронеж",),
    "irkutsk": ("иркут",),
    "krasnoyarsk": ("красноярск",),
    "vladivostok": ("владивост", "примор"),
    "all": (),  # pseudo-region: any news
}


# news category → spas scenario id (best-effort triage)
_CATEGORY_TO_SCENARIO: dict[str, str] = {
    "наводн": "utopanie",
    "пожар": "ozhog",
    "землетряс": "earthquake_safety",
    "лавин": "hypothermia",
    "ураган": "shelter_in_place",
    "химичес": "anafilaksiya",
    "ливен": "shelter_in_place",
    "лед": "hypothermia",
}


@dataclass(frozen=True)
class Alert:
    guid: str
    title: str
    link: str
    description: str
    category: str | None


def _strip_html(s: str) -> str:
    out: list[str] = []
    in_tag = False
    for ch in s:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            out.append(ch)
    return "".join(out).strip()


def parse_rss(xml_bytes: bytes) -> list[Alert]:
    """Parse RSS 2.0 bytes into a list of :class:`Alert`."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        log.warning("rss parse failed: %s", exc)
        return []

    items_xml = root.findall(".//item")
    alerts: list[Alert] = []
    for it in items_xml:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link or title)[:200]
        description = _strip_html(it.findtext("description") or "")
        category = (it.findtext("category") or "").strip().lower() or None
        if not title and not description:
            continue
        alerts.append(
            Alert(
                guid=guid,
                title=title,
                link=link,
                description=description,
                category=category,
            )
        )
    return alerts


def match_region(alert: Alert, region: str) -> bool:
    """Return True if alert text mentions the region."""
    region = region.strip().lower()
    if region == "all":
        return True
    haystack = (alert.title + " " + alert.description).lower()
    for pat in _REGION_MATCHERS.get(region, ()):
        if pat in haystack:
            return True
    return region in haystack


def map_to_scenario(alert: Alert) -> str | None:
    """Try to map a news category/title to a SPAS scenario id."""
    haystack = (alert.title + " " + (alert.category or "")).lower()
    for key, sid in _CATEGORY_TO_SCENARIO.items():
        if key in haystack:
            return sid
    return None


def render_alert(alert: Alert, *, scenario: str | None) -> str:
    body = [f"🚨 <b>МЧС</b>: {alert.title or '(без заголовка)'}"]
    if alert.description:
        body.append(alert.description[:500])
    if alert.link:
        body.append(alert.link)
    if scenario:
        body.append(f"\nЕсли касается тебя — открой сценарий: /scn_{scenario}")
    return "\n".join(body)


async def fetch_rss(url: str = _DEFAULT_URL) -> list[Alert]:
    try:
        async with (
            aiohttp.ClientSession() as s,
            s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r,
        ):
            r.raise_for_status()
            body = await r.read()
    except Exception as exc:
        log.warning("rss fetch failed: %s", exc)
        return []
    return parse_rss(body)


async def deliver_alerts(
    storage: Storage,
    alerts: Iterable[Alert],
    *,
    send: AsyncSender,
) -> int:
    """For each alert, find subscribers per region and call ``send(user_id, text)``.

    ``send`` is a coroutine ``(user_id, text) -> None``.

    Returns the number of *delivered* messages (best-effort; failed sends are skipped).
    """
    delivered = 0
    for alert in alerts:
        if await storage.alert_seen(alert.guid):
            continue
        scenario = map_to_scenario(alert)
        text = render_alert(alert, scenario=scenario)
        # Iterate all known regions; only those matching get notifications.
        for region in _REGION_MATCHERS:
            if not match_region(alert, region):
                continue
            users = await storage.subscribers_for_region(region)
            for uid in users:
                try:
                    await send(uid, text)  # type: ignore[misc]
                    delivered += 1
                except Exception as exc:
                    log.warning("alert send to %s failed: %s", uid, exc)
        await storage.mark_alert_seen(alert.guid)
    return delivered


async def poll_loop(storage: Storage, send: AsyncSender, *, interval_sec: float = 900.0) -> None:
    """Background loop. Cancel by cancelling the task."""
    url = os.getenv("MCHS_RSS_URL", _DEFAULT_URL)
    log.info("МЧС RSS poll started (url=%s, every %.0fs)", url, interval_sec)
    while True:
        try:
            alerts = await fetch_rss(url)
            if alerts:
                count = await deliver_alerts(storage, alerts, send=send)
                if count:
                    log.info("delivered %d alerts", count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("rss loop iter failed: %s", exc)
        await asyncio.sleep(interval_sec)


def known_regions() -> list[str]:
    """Return supported region keys (used in /subscribe_alerts help)."""
    return [r for r in _REGION_MATCHERS if r != "all"] + ["all"]
