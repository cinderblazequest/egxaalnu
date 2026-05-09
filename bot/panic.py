"""Panic-режим: успокаивающее дыхание + grounding + быстрый triage."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger("spas.panic")


@dataclass(frozen=True)
class TriageOption:
    id: str
    label: str
    scenario: str | None
    message: str


@dataclass(frozen=True)
class PanicProtocol:
    intro: str
    breathing_intro: str
    breathing_cycle_seconds: int
    breathing_total_cycles: int
    breathing_inhale: str
    breathing_hold: str
    breathing_exhale: str
    grounding_title: str
    grounding_lines: tuple[str, ...]
    grounding_outro: str
    triage: tuple[TriageOption, ...]
    disclaimer: str


def load_panic_protocol(content_dir: Path) -> PanicProtocol:
    raw = json.loads((content_dir / "panic_protocol.json").read_text(encoding="utf-8"))
    breathing = raw["breathing"]
    grounding = raw["grounding"]
    triage = tuple(
        TriageOption(
            id=item["id"],
            label=item["label"],
            scenario=item.get("scenario"),
            message=item["message"],
        )
        for item in raw["triage"]
    )
    return PanicProtocol(
        intro=raw["intro"],
        breathing_intro=f"<b>{breathing['title']}</b>\n{breathing['instructions']}",
        breathing_cycle_seconds=int(breathing["cycle_seconds"]),
        breathing_total_cycles=int(breathing["total_cycles"]),
        breathing_inhale=breathing["inhale_text"],
        breathing_hold=breathing["hold_text"],
        breathing_exhale=breathing["exhale_text"],
        grounding_title=f"<b>{grounding['title']}</b>",
        grounding_lines=tuple(grounding["lines"]),
        grounding_outro=grounding["outro"],
        triage=triage,
        disclaimer=raw["disclaimer"],
    )


def panic_intro_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌬️ Подышать со мной 6/мин", callback_data="panic:breathe")],
            [InlineKeyboardButton(text="🪨 Упражнение 5-4-3-2-1", callback_data="panic:ground")],
            [InlineKeyboardButton(text="🆘 Что случилось?", callback_data="panic:triage")],
            [InlineKeyboardButton(text="« в меню", callback_data="menu:home")],
        ]
    )


def triage_kb(protocol: PanicProtocol) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=opt.label, callback_data=f"panic_t:{opt.id}")] for opt in protocol.triage
    ]
    rows.append([InlineKeyboardButton(text="« назад", callback_data="panic:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_panic_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« в panic-меню", callback_data="panic:home")],
            [InlineKeyboardButton(text="« в главное меню", callback_data="menu:home")],
        ]
    )


def find_triage(protocol: PanicProtocol, option_id: str) -> TriageOption | None:
    for opt in protocol.triage:
        if opt.id == option_id:
            return opt
    return None


async def run_breathing(
    bot: Bot,
    chat_id: int,
    protocol: PanicProtocol,
    *,
    sleep: object | None = None,
) -> None:
    """Анимированный текстовый таймер дыхания.

    sleep — для тестов: callable, возвращающий awaitable. По умолчанию asyncio.sleep.
    """
    sleep_fn = sleep if sleep is not None else asyncio.sleep
    msg = await bot.send_message(chat_id, protocol.breathing_intro)
    cycle = max(int(protocol.breathing_cycle_seconds), 6)
    inhale_s, hold_s, exhale_s = 4, 1, max(cycle - 5, 1)
    for i in range(protocol.breathing_total_cycles):
        for phase_text, secs in (
            (protocol.breathing_inhale, inhale_s),
            (protocol.breathing_hold, hold_s),
            (protocol.breathing_exhale, exhale_s),
        ):
            try:
                await msg.edit_text(
                    f"<b>Цикл {i + 1} из {protocol.breathing_total_cycles}</b>\n\n{phase_text}"
                )
            except Exception as exc:
                log.debug("breathing edit_text failed: %s", exc)
            await sleep_fn(secs)
    try:
        await msg.edit_text(
            f"✅ Готово. Ты прошёл(ла) {protocol.breathing_total_cycles} цикла.\n\n" f"{protocol.disclaimer}",
            reply_markup=back_to_panic_kb(),
        )
    except Exception as exc:
        log.debug("breathing final edit_text failed: %s", exc)
