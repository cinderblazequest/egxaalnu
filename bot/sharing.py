"""Семейный share: сгенерировать deep-link сообщения для родителей/друзей.

Не отправляет сам — даёт пользователю готовый текст + кнопку
``url=https://t.me/share/url?url=...&text=...``, которую Telegram
рендерит как share sheet.
"""

from __future__ import annotations

from urllib.parse import quote

from bot.gamification import level_for_xp


def share_progress_text(*, full_name: str | None, xp_state: dict, bot_username: str) -> str:
    xp = int(xp_state.get("xp", 0))
    level, label = level_for_xp(xp)
    streak = int(xp_state.get("streak_days", 0))
    achievements = xp_state.get("achievements") or []
    name = full_name or "Я"
    parts = [
        f"{name} учится первой помощи в боте СПАС",
        f"уровень: {level} · {label}",
        f"XP: {xp}",
    ]
    if streak >= 3:
        parts.append(f"серия: {streak} дней подряд")
    if achievements:
        parts.append(f"ачивок: {len(achievements)}")
    parts.append(f"бот: https://t.me/{bot_username}")
    return " — ".join(parts)


def share_certificate_text(*, full_name: str, code: str, bot_username: str) -> str:
    return (
        f"Я получил(а) сертификат участника пилота СПАС. "
        f"Код: {code}. Бот: https://t.me/{bot_username}?start=cert_{code}. "
        f"Это: {full_name}"
    )


def telegram_share_url(text: str) -> str:
    return f"https://t.me/share/url?url={quote(text, safe='')}"
