"""Tests for sos message rendering and map link helpers."""

from __future__ import annotations

from bot.sos import (
    google_maps_link,
    osm_link,
    render_sos_message,
    telegram_share_url,
    yandex_maps_link,
)


def test_google_maps_link_format() -> None:
    link = google_maps_link(55.7558, 37.6173)
    assert "maps.google.com" in link
    assert "55.755800" in link
    assert "37.617300" in link


def test_yandex_maps_link_format() -> None:
    link = yandex_maps_link(55.7558, 37.6173)
    assert "yandex.ru/maps" in link
    # yandex carries lon first
    assert "37.617300,55.755800" in link


def test_osm_link_format() -> None:
    link = osm_link(55.7558, 37.6173)
    assert "openstreetmap.org" in link
    assert "mlat=55.755800" in link


def test_render_sos_message_includes_links_and_phone() -> None:
    msg = render_sos_message(name="Аня", lat=55.7558, lon=37.6173, note=None)
    assert "Аня" in msg
    assert "Google Maps" in msg
    assert "Яндекс" in msg
    assert "OpenStreetMap" in msg
    assert "112" in msg


def test_render_sos_message_with_note_truncates_long() -> None:
    note = "x" * 1000
    msg = render_sos_message(name="A", lat=0.0, lon=0.0, note=note)
    # Should not include the entire 1000-char string
    assert msg.count("x") <= 305


def test_render_sos_message_without_name_uses_default() -> None:
    msg = render_sos_message(name=None, lat=10.0, lon=20.0, note=None)
    assert "пользователь СПАС" in msg


def test_telegram_share_url_encodes() -> None:
    url = telegram_share_url("hello world & more")
    assert url.startswith("https://t.me/share/url?url=")
    # space and & are encoded
    assert "%20" in url or "+" in url
    assert "%26" in url
