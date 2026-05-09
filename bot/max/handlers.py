"""Обработчики команд и callback'ов для Max-бота СПАС.

Этот модуль — тонкий «адаптер» поверх контента, который уже есть в
``content/scenarios.json``, ``content/dispatcher_checklist.json``,
``content/panic_protocol.json`` и ``content/aed_locations.json``.
Он переиспользует:
- ``bot.catalogue.Catalogue`` — все 30 сценариев и точки АНД,
- ``bot.dispatcher.load_dispatcher`` — чек-лист 112,
- ``bot.panic.load_panic`` — панический протокол.

Команды:
    /start         — приветствие и меню;
    /sos           — категоризированный список сценариев;
    /panic         — успокоительный протокол;
    /dispatcher    — чек-лист 112;
    /aed           — список ближайших АНД (по умолчанию — 5 штук);
    /scenarios <id> — открыть конкретный сценарий;
    /help          — помощь.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.catalogue import Catalogue, Scenario
from bot.dispatcher import load_dispatcher_checklist
from bot.max.client import MaxBotClient, MaxButton
from bot.panic import load_panic_protocol

log = logging.getLogger("spas.max.handlers")

CB_OPEN_PREFIX = "open:"  # open:<scenario_id>
CB_CAT_PREFIX = "cat:"  # cat:critical|urgent|minor


WELCOME_TEXT = (
    "👋 Привет! Я СПАС — карманный AI-помощник по первой помощи.\n\n"
    "Я могу провести через 30 сценариев первой помощи, помочь успокоиться "
    "(/panic), собрать сообщение для оператора 112 (/dispatcher) и показать "
    "ближайшие АНД (/aed).\n\n"
    "⚠ Я не заменяю врачей. Если есть угроза жизни — звони 112."
)

HELP_TEXT = (
    "Команды:\n"
    "/sos — список сценариев первой помощи (по категориям)\n"
    "/panic — панический протокол (дыхание + заземление)\n"
    "/dispatcher — собрать сообщение для 112\n"
    "/aed — ближайшие точки АНД\n"
    "/scenarios <id> — открыть сценарий\n"
    "/help — это сообщение"
)


@dataclass(frozen=True)
class MaxAppContext:
    catalogue: Catalogue
    dispatcher: Any  # bot.dispatcher.DispatcherChecklist (Pydantic)
    panic: Any  # bot.panic.PanicProtocol


def build_context(content_dir: Path) -> MaxAppContext:
    return MaxAppContext(
        catalogue=Catalogue(content_dir),
        dispatcher=load_dispatcher_checklist(content_dir),
        panic=load_panic_protocol(content_dir),
    )


def main_menu_buttons() -> list[list[MaxButton]]:
    return [
        [MaxButton("🚑 СОС-сценарии", CB_CAT_PREFIX + "critical")],
        [MaxButton("⚠ Срочные", CB_CAT_PREFIX + "urgent")],
        [MaxButton("🩹 Лёгкие", CB_CAT_PREFIX + "minor")],
        [MaxButton("😰 Паника", "cmd:panic"), MaxButton("📞 112", "cmd:dispatcher")],
        [MaxButton("📍 АНД", "cmd:aed"), MaxButton("ℹ Помощь", "cmd:help")],
    ]


def category_buttons(scenarios: list[Scenario]) -> list[list[MaxButton]]:
    return [[MaxButton(f"{s.icon} {s.title}", CB_OPEN_PREFIX + s.id)] for s in scenarios[:30]]


def render_scenario(scenario: Scenario) -> str:
    body = [f"{scenario.icon} <b>{scenario.title}</b>", "", scenario.summary, ""]
    body.extend(f"{i}. {step}" for i, step in enumerate(scenario.steps, 1))
    body.append("")
    body.append(f"☎ Если ситуация ухудшается — звони {scenario.phone}")
    return "\n".join(body)


def render_panic_intro(panic: Any) -> str:
    return (
        f"🌬 <b>Паника? Это ок.</b>\n\n{panic.intro}\n\n"
        f"📋 <i>Дыхание — {panic.breathing_total_cycles} циклов</i>\n"
        f"{panic.breathing_intro}"
    )


def render_dispatcher_intro(checklist: Any) -> str:
    lines = ["📞 <b>Чек-лист для 112</b>", "", checklist.intro, ""]
    for q in checklist.questions:
        lines.append(f"• {q.label}")
    lines.append("")
    lines.append("Соберу полный текст звонка по этим пунктам, отправь /sos если ситуация острая.")
    return "\n".join(lines)


def render_aed_list(catalogue: Catalogue, *, limit: int = 5) -> str:
    lines = ["📍 <b>Точки АНД (автоматический наружный дефибриллятор)</b>", ""]
    for loc in catalogue.aed[:limit]:
        note = f" — {loc.note}" if loc.note else ""
        lines.append(f"• {loc.city}, {loc.name}{note}\n  {loc.lat:.4f}, {loc.lon:.4f}")
    lines.append("")
    lines.append(f"Всего в базе: {len(catalogue.aed)}.")
    return "\n".join(lines)


async def handle_command(client: MaxBotClient, ctx: MaxAppContext, chat_id: int, text: str) -> None:
    cmd, *rest = text.strip().split(maxsplit=1)
    arg = rest[0] if rest else ""
    cmd = cmd.lower()
    if cmd in ("/start", "/help"):
        await client.send_message(chat_id, WELCOME_TEXT, buttons=main_menu_buttons())
        if cmd == "/help":
            await client.send_message(chat_id, HELP_TEXT)
        return
    if cmd == "/sos":
        await client.send_message(
            chat_id,
            "🚑 <b>Сценарии первой помощи</b>\nВыбери категорию:",
            buttons=main_menu_buttons(),
        )
        return
    if cmd == "/panic":
        await client.send_message(chat_id, render_panic_intro(ctx.panic))
        return
    if cmd == "/dispatcher":
        await client.send_message(chat_id, render_dispatcher_intro(ctx.dispatcher))
        return
    if cmd == "/aed":
        await client.send_message(chat_id, render_aed_list(ctx.catalogue))
        return
    if cmd == "/scenarios":
        scenario = ctx.catalogue.scenarios.get(arg)
        if scenario is None:
            await client.send_message(chat_id, "Неизвестный id сценария. Открой /sos и выбери из меню.")
            return
        await client.send_message(chat_id, render_scenario(scenario))
        return
    await client.send_message(chat_id, "Не понял команду. Открой /help.")


async def handle_callback(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    callback_id: str,
    payload: str,
) -> None:
    if payload.startswith(CB_CAT_PREFIX):
        cat = payload[len(CB_CAT_PREFIX) :]
        scenarios = {
            "critical": ctx.catalogue.list_critical(),
            "urgent": ctx.catalogue.list_urgent(),
            "minor": ctx.catalogue.list_minor(),
        }.get(cat, [])
        if not scenarios:
            await client.answer_callback(callback_id, notification="Категория пуста")
            return
        await client.send_message(
            chat_id,
            f"Выбери сценарий ({cat}, {len(scenarios)}):",
            buttons=category_buttons(scenarios),
        )
        await client.answer_callback(callback_id)
        return
    if payload.startswith(CB_OPEN_PREFIX):
        sid = payload[len(CB_OPEN_PREFIX) :]
        scenario = ctx.catalogue.scenarios.get(sid)
        if scenario is None:
            await client.answer_callback(callback_id, notification="Сценарий не найден")
            return
        await client.send_message(chat_id, render_scenario(scenario))
        await client.answer_callback(callback_id)
        return
    if payload == "cmd:panic":
        await client.send_message(chat_id, render_panic_intro(ctx.panic))
        await client.answer_callback(callback_id)
        return
    if payload == "cmd:dispatcher":
        await client.send_message(chat_id, render_dispatcher_intro(ctx.dispatcher))
        await client.answer_callback(callback_id)
        return
    if payload == "cmd:aed":
        await client.send_message(chat_id, render_aed_list(ctx.catalogue))
        await client.answer_callback(callback_id)
        return
    if payload == "cmd:help":
        await client.send_message(chat_id, HELP_TEXT)
        await client.answer_callback(callback_id)
        return
    await client.answer_callback(callback_id, notification="Неизвестная команда")


def extract_chat_id(update: dict[str, Any]) -> int | None:
    """Достать ``chat_id`` из любого типа апдейта Max."""
    msg = update.get("message")
    if msg and isinstance(msg, dict):
        recipient = msg.get("recipient") or {}
        if "chat_id" in recipient:
            return int(recipient["chat_id"])
        sender = msg.get("sender") or {}
        if "user_id" in sender:
            return int(sender["user_id"])
    cb = update.get("callback")
    if cb and isinstance(cb, dict):
        msg = update.get("message") or {}
        recipient = msg.get("recipient") or {}
        if "chat_id" in recipient:
            return int(recipient["chat_id"])
        user = cb.get("user") or {}
        if "user_id" in user:
            return int(user["user_id"])
    if "chat_id" in update:
        return int(update["chat_id"])
    return None


async def dispatch_update(client: MaxBotClient, ctx: MaxAppContext, update: dict[str, Any]) -> None:
    """Маршрутизация одного апдейта."""
    update_type = update.get("update_type") or update.get("type")
    chat_id = extract_chat_id(update)
    if update_type == "message_created":
        message = update.get("message") or {}
        body = (message.get("body") or {}).get("text", "")
        if not body or chat_id is None:
            return
        await handle_command(client, ctx, chat_id, body)
        return
    if update_type == "message_callback":
        cb = update.get("callback") or {}
        payload = cb.get("payload", "")
        callback_id = cb.get("callback_id", "")
        if not callback_id or chat_id is None:
            return
        await handle_callback(client, ctx, chat_id=chat_id, callback_id=callback_id, payload=payload)
        return
    if update_type in ("bot_started", "bot_added"):
        if chat_id is not None:
            await client.send_message(chat_id, WELCOME_TEXT, buttons=main_menu_buttons())
        return
    log.debug("Игнорируем тип апдейта: %s", update_type)
