"""SOS-команда: расшарить геолокацию и текст помощи доверенному контакту.

Workflow:
  /setup_sos — задать доверенный контакт (через forward от него либо чат-id)
  /sos_share — отправить сообщение «помоги, я тут <карта>» в этот контакт
  /sos_clear — забыть контакт

Если контакт не задан — кнопка-инструкция и ссылка ``tg://...``, плюс
сразу напоминание звонить 112.
"""

from __future__ import annotations

from urllib.parse import quote


def google_maps_link(lat: float, lon: float) -> str:
    return f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"


def yandex_maps_link(lat: float, lon: float) -> str:
    return f"https://yandex.ru/maps/?pt={lon:.6f},{lat:.6f}&z=18"


def osm_link(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}" f"#map=18/{lat:.6f}/{lon:.6f}"


def render_sos_message(*, name: str | None, lat: float, lon: float, note: str | None) -> str:
    who = name or "пользователь СПАС"
    base = (
        f"🆘 SOS! {who} просит помощи прямо сейчас.\n\n"
        f"📍 Геолокация:\n"
        f"• Google Maps: {google_maps_link(lat, lon)}\n"
        f"• Яндекс Карты: {yandex_maps_link(lat, lon)}\n"
        f"• OpenStreetMap: {osm_link(lat, lon)}\n"
    )
    if note:
        base += f"\n💬 {note[:300]}\n"
    base += (
        "\nПожалуйста, позвони ему/ей и набери 112 от своего номера.\n"
        "Это автоматический сигнал из бота СПАС."
    )
    return base


def telegram_share_url(text: str) -> str:
    """Build a tg://msg_url link for share sheet (inline keyboard ``url=``)."""
    return f"https://t.me/share/url?url={quote(text, safe='')}"
