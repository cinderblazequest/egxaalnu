"""Обработчики команд и callback'ов для Max-бота СПАС.

Этот модуль — тонкий «адаптер» поверх контента, который уже есть в
``content/scenarios.json``, ``content/dispatcher_checklist.json``,
``content/panic_protocol.json`` и ``content/aed_locations.json``.
Он переиспользует:
- ``bot.catalogue.Catalogue`` — все 30 сценариев и точки АНД,
- ``bot.dispatcher.load_dispatcher`` — чек-лист 112,
- ``bot.panic.load_panic`` — панический протокол,
- ``bot.gamification.evaluate_event`` — XP / ачивки / стрик,
- ``bot.certificate.build_certificate_code`` — выдача сертификата.

Команды:
    /start         — приветствие и меню;
    /sos           — категоризированный список сценариев;
    /panic         — успокоительный протокол;
    /dispatcher    — чек-лист 112;
    /aed           — список ближайших АНД;
    /scenarios <id> — открыть конкретный сценарий пошагово (с pre/post-тестом);
    /profile       — XP, уровень, ачивки;
    /leaderboard   — топ-10 по XP;
    /help          — помощь.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.catalogue import Catalogue, Scenario, TestQuestion
from bot.certificate import build_certificate_code
from bot.dispatcher import load_dispatcher_checklist
from bot.gamification import ACHIEVEMENTS, evaluate_event, render_profile
from bot.max.client import MaxBotClient, MaxButton
from bot.max.state import MaxStateMachine, ScenarioStepState
from bot.panic import load_panic_protocol
from bot.storage import Storage

log = logging.getLogger("spas.max.handlers")

CB_OPEN_PREFIX = "open:"  # open:<scenario_id>
CB_CAT_PREFIX = "cat:"  # cat:critical|urgent|minor
CB_STEP_PREFIX = "step:"  # step:<sid>:<idx>
CB_NEXT_PREFIX = "next:"  # next:<sid>
CB_PREV_PREFIX = "prev:"  # prev:<sid>
CB_PRE_PREFIX = "pre:"  # pre:<sid>:<qidx>:<option>
CB_POST_PREFIX = "post:"  # post:<sid>:<qidx>:<option>
CB_METRO_PREFIX = "metro:"  # metro:<sid>
CB_FINISH_PREFIX = "fin:"  # fin:<sid>


WELCOME_TEXT = (
    "👋 Привет! Я СПАС — карманный AI-помощник по первой помощи.\n\n"
    "Я могу провести через 30 сценариев первой помощи (пошагово, с тестами "
    "до и после), помочь успокоиться (/panic), собрать сообщение для оператора "
    "112 (/dispatcher) и показать ближайшие АНД (/aed).\n\n"
    "⚠ Я не заменяю врачей. Если есть угроза жизни — звони 112."
)

HELP_TEXT = (
    "Команды:\n"
    "/sos — список сценариев первой помощи (по категориям)\n"
    "/panic — панический протокол (дыхание + заземление)\n"
    "/dispatcher — собрать сообщение для 112\n"
    "/aed — ближайшие точки АНД\n"
    "/scenarios <id> — открыть сценарий пошагово\n"
    "/profile — мой профиль (XP, уровень, ачивки)\n"
    "/leaderboard — топ-10 по XP\n"
    "/help — это сообщение"
)


@dataclass
class MaxAppContext:
    catalogue: Catalogue
    dispatcher: Any  # bot.dispatcher.DispatcherChecklist (Pydantic)
    panic: Any  # bot.panic.PanicProtocol
    state: MaxStateMachine
    storage: Storage | None = None


def build_context(content_dir: Path, *, storage: Storage | None = None) -> MaxAppContext:
    return MaxAppContext(
        catalogue=Catalogue(content_dir),
        dispatcher=load_dispatcher_checklist(content_dir),
        panic=load_panic_protocol(content_dir),
        state=MaxStateMachine(),
        storage=storage,
    )


def main_menu_buttons() -> list[list[MaxButton]]:
    return [
        [MaxButton("🚑 СОС-сценарии", CB_CAT_PREFIX + "critical")],
        [MaxButton("⚠ Срочные", CB_CAT_PREFIX + "urgent")],
        [MaxButton("🩹 Лёгкие", CB_CAT_PREFIX + "minor")],
        [MaxButton("😰 Паника", "cmd:panic"), MaxButton("📞 112", "cmd:dispatcher")],
        [MaxButton("📍 АНД", "cmd:aed"), MaxButton("🎓 Профиль", "cmd:profile")],
        [MaxButton("ℹ Помощь", "cmd:help")],
    ]


def category_buttons(scenarios: list[Scenario]) -> list[list[MaxButton]]:
    return [[MaxButton(f"{s.icon} {s.title}", CB_OPEN_PREFIX + s.id)] for s in scenarios[:30]]


def render_scenario_intro(scenario: Scenario) -> str:
    """Краткая карточка перед началом прохождения."""
    return (
        f"{scenario.icon} <b>{scenario.title}</b>\n"
        f"<i>{scenario.summary}</i>\n\n"
        f"📞 Экстренный: {scenario.phone}\n"
        f"Шагов: {len(scenario.steps)}"
    )


def render_step(scenario: Scenario, idx: int) -> str:
    """Текст одного шага сценария с прогрессом."""
    return (
        f"{scenario.icon} <b>{scenario.title}</b>\n"
        f"<b>Шаг {idx + 1} из {len(scenario.steps)}</b>\n\n"
        f"{scenario.steps[idx]}\n\n"
        f"📞 Если ухудшается — {scenario.phone}"
    )


def step_buttons(scenario_id: str, idx: int, total: int, *, with_metronome: bool) -> list[list[MaxButton]]:
    nav: list[MaxButton] = []
    if idx > 0:
        nav.append(MaxButton("« Назад", CB_PREV_PREFIX + scenario_id))
    if idx < total - 1:
        nav.append(MaxButton("Дальше »", CB_NEXT_PREFIX + scenario_id))
    else:
        nav.append(MaxButton("✅ К пост-тесту", CB_NEXT_PREFIX + scenario_id))
    rows: list[list[MaxButton]] = [nav]
    if with_metronome:
        rows.append([MaxButton("🥁 Метроном 100 BPM", CB_METRO_PREFIX + scenario_id)])
    rows.append([MaxButton("📞 112", "cmd:dispatcher"), MaxButton("⏹ Меню", "cmd:menu")])
    return rows


def test_buttons(scenario_id: str, phase: str, q_idx: int, question: TestQuestion) -> list[list[MaxButton]]:
    prefix = CB_PRE_PREFIX if phase == "pre" else CB_POST_PREFIX
    return [
        [MaxButton(f"{i + 1}. {opt}", f"{prefix}{scenario_id}:{q_idx}:{i}")]
        for i, opt in enumerate(question.options)
    ]


def render_test_question(scenario: Scenario, phase: str, q_idx: int) -> str:
    bank = scenario.pre_test if phase == "pre" else scenario.post_test
    q = bank[q_idx]
    header = "🧠 Pre-test" if phase == "pre" else "🧠 Post-test"
    return f"{header} · <b>{scenario.title}</b>\n" f"Вопрос {q_idx + 1} из {len(bank)}\n\n" f"{q.q}"


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


def render_metronome_text(*, bpm: int = 100, seconds: int = 12) -> str:
    """Текстовый метроном — без аудио, потому что Max не во всех клиентах
    одинаково воспроизводит файлы. Имитация: «РАЗ ... ДВА ... ТРИ» с
    указанным темпом, чтобы пользователь синхронизировал компрессии."""
    beats = bpm * seconds // 60
    ticks = " · ".join(["♥"] * min(beats, 20))
    return (
        f"🥁 <b>Метроном {bpm} BPM</b>\n\n"
        f"Жми вместе с каждым «♥» — это темп компрессий для СЛР.\n\n"
        f"{ticks}\n\n"
        f"Реальный звук — в Telegram-версии бота. В Max используй визуальный темп."
    )


async def _award_xp_and_certificate(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    user_id: int,
    scenario_id: str,
    post_correct: int,
    post_total: int,
) -> None:
    """Начислить XP за прохождение, выдать ачивки, при ≥ 3 сценариях — код сертификата.

    Без storage всё равно отправляем поздравление, чтобы пользователь видел финал.
    """
    storage = ctx.storage
    if storage is None:
        congrats = [
            "🎉 <b>Сценарий пройден!</b>",
            f"Post-test: {post_correct}/{post_total}" if post_total else "",
            "XP/ачивки появятся, когда бот будет запущен с базой данных.",
        ]
        await client.send_message(
            chat_id, "\n".join(line for line in congrats if line), buttons=main_menu_buttons()
        )
        return
    try:
        await storage.upsert_user(user_id, None)
    except Exception:
        log.debug("upsert_user пропущен", exc_info=True)
    try:
        await storage.log_event(user_id, "scenario_complete", scenario_id)
        if post_total:
            await storage.save_test(user_id, scenario_id, "post", post_correct, post_total)
    except Exception:
        log.debug("log_event/save_test пропущены", exc_info=True)
    try:
        completed_total = await storage.count_distinct_completed_scenarios(user_id)
    except Exception:
        completed_total = 1
    perfect = bool(post_total) and post_correct == post_total
    state = await storage.get_xp(user_id)
    delta = evaluate_event(
        state=state,
        event="scenario_complete",
        payload=scenario_id,
        completed_scenarios={scenario_id},
        perfect_post=perfect,
    )
    await storage.save_xp(
        user_id,
        xp=state["xp"] + delta.xp_gained,
        level=delta.new_level,
        achievements=list({*state.get("achievements", []), *(a.code for a in delta.new_achievements)}),
        streak_days=delta.streak_days,
        last_active=_dt.datetime.now(_dt.UTC).isoformat(),
    )

    parts = [
        "🎉 <b>Сценарий пройден!</b>",
        f"+{delta.xp_gained} XP · уровень {delta.new_level} ({delta.new_label})",
        f"Сценариев пройдено всего: {completed_total}",
    ]
    if delta.new_achievements:
        parts.append("")
        parts.append("🏅 Новые ачивки:")
        for a in delta.new_achievements:
            parts.append(f"• {a.title} — {a.description}")
    if completed_total >= 3:
        code = build_certificate_code(user_id, completed_total, _dt.datetime.now(_dt.UTC))
        parts.append("")
        parts.append(f"🎓 <b>Код твоего сертификата:</b> <code>{code}</code>")
        parts.append("Покажи учителю или сохрани — это публичный verifier-код.")
    await client.send_message(chat_id, "\n".join(parts), buttons=main_menu_buttons())


async def _show_step(
    client: MaxBotClient,
    scenario: Scenario,
    chat_id: int,
    state: ScenarioStepState,
) -> None:
    await client.send_message(
        chat_id,
        render_step(scenario, state.step_idx),
        buttons=step_buttons(
            scenario.id, state.step_idx, len(scenario.steps), with_metronome=scenario.metronome
        ),
    )


async def _show_test_question(
    client: MaxBotClient,
    scenario: Scenario,
    chat_id: int,
    phase: str,
    q_idx: int,
) -> None:
    bank = scenario.pre_test if phase == "pre" else scenario.post_test
    if q_idx >= len(bank):
        return
    await client.send_message(
        chat_id,
        render_test_question(scenario, phase, q_idx),
        buttons=test_buttons(scenario.id, phase, q_idx, bank[q_idx]),
    )


async def _start_scenario(
    client: MaxBotClient,
    ctx: MaxAppContext,
    chat_id: int,
    user_id: int,
    scenario: Scenario,
) -> None:
    has_pre = bool(scenario.pre_test)
    state = await ctx.state.start_scenario(user_id, scenario.id, has_pre_test=has_pre)
    if ctx.storage is not None:
        try:
            await ctx.storage.log_event(user_id, "scenario_open", scenario.id)
        except Exception:
            log.debug("log_event scenario_open пропущен", exc_info=True)
    await client.send_message(chat_id, render_scenario_intro(scenario))
    if state.phase == "pre":
        await _show_test_question(client, scenario, chat_id, "pre", 0)
    else:
        await _show_step(client, scenario, chat_id, state)


async def handle_command(
    client: MaxBotClient,
    ctx: MaxAppContext,
    chat_id: int,
    user_id: int,
    text: str,
) -> None:
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
    if cmd == "/profile":
        if ctx.storage is None:
            await client.send_message(chat_id, "Профиль доступен на сервере с базой данных.")
            return
        state = await ctx.storage.get_xp(user_id)
        await client.send_message(chat_id, render_profile(state), buttons=main_menu_buttons())
        return
    if cmd == "/leaderboard":
        if ctx.storage is None:
            await client.send_message(chat_id, "Лидерборд доступен на сервере с базой данных.")
            return
        rows = await ctx.storage.leaderboard(limit=10)
        if not rows:
            await client.send_message(chat_id, "Лидерборд пуст. Стань первым: /sos")
            return
        lines = ["🏆 <b>Топ-10 СПАС</b>", ""]
        for i, r in enumerate(rows, 1):
            name = r["username"] or f"#{r['user_id']}"
            lines.append(f"{i}. {name} — {r['xp']} XP (lvl {r['level']})")
        await client.send_message(chat_id, "\n".join(lines))
        return
    if cmd == "/scenarios":
        scenario = ctx.catalogue.scenarios.get(arg)
        if scenario is None:
            await client.send_message(chat_id, "Неизвестный id сценария. Открой /sos и выбери из меню.")
            return
        await _start_scenario(client, ctx, chat_id, user_id, scenario)
        return
    await client.send_message(chat_id, "Не понял команду. Открой /help.")


async def _resolve_scenario_or_warn(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    callback_id: str,
    scenario_id: str,
) -> Scenario | None:
    scenario = ctx.catalogue.scenarios.get(scenario_id)
    if scenario is None:
        await client.answer_callback(callback_id, notification="Сценарий не найден")
    return scenario


async def _handle_category(
    client: MaxBotClient, ctx: MaxAppContext, chat_id: int, callback_id: str, payload: str
) -> None:
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


async def _handle_open(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    user_id: int,
    callback_id: str,
    payload: str,
) -> None:
    sid = payload[len(CB_OPEN_PREFIX) :]
    scenario = await _resolve_scenario_or_warn(
        client, ctx, chat_id=chat_id, callback_id=callback_id, scenario_id=sid
    )
    if scenario is None:
        return
    await _start_scenario(client, ctx, chat_id, user_id, scenario)
    await client.answer_callback(callback_id)


async def _handle_next(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    user_id: int,
    callback_id: str,
    payload: str,
) -> None:
    sid = payload[len(CB_NEXT_PREFIX) :]
    scenario = await _resolve_scenario_or_warn(
        client, ctx, chat_id=chat_id, callback_id=callback_id, scenario_id=sid
    )
    if scenario is None:
        return
    state = await ctx.state.next_step(user_id, max_steps=len(scenario.steps))
    if state is None:
        await client.answer_callback(callback_id, notification="Сначала открой сценарий")
        return
    if state.phase == "post":
        if scenario.post_test:
            await _show_test_question(client, scenario, chat_id, "post", 0)
        else:
            await ctx.state.finish(user_id)
            await _award_xp_and_certificate(
                client,
                ctx,
                chat_id=chat_id,
                user_id=user_id,
                scenario_id=scenario.id,
                post_correct=0,
                post_total=0,
            )
    else:
        await _show_step(client, scenario, chat_id, state)
    await client.answer_callback(callback_id)


async def _handle_prev(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    user_id: int,
    callback_id: str,
    payload: str,
) -> None:
    sid = payload[len(CB_PREV_PREFIX) :]
    scenario = await _resolve_scenario_or_warn(
        client, ctx, chat_id=chat_id, callback_id=callback_id, scenario_id=sid
    )
    if scenario is None:
        return
    state = await ctx.state.prev_step(user_id)
    if state is None:
        await client.answer_callback(callback_id, notification="Сначала открой сценарий")
        return
    await _show_step(client, scenario, chat_id, state)
    await client.answer_callback(callback_id)


async def _handle_test_answer(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    user_id: int,
    callback_id: str,
    payload: str,
    phase: str,
) -> None:
    prefix = CB_PRE_PREFIX if phase == "pre" else CB_POST_PREFIX
    rest = payload[len(prefix) :]
    try:
        sid, q_idx_s, choice_s = rest.split(":")
        q_idx = int(q_idx_s)
        choice = int(choice_s)
    except ValueError:
        await client.answer_callback(callback_id, notification="Ошибка формата ответа")
        return
    scenario = await _resolve_scenario_or_warn(
        client, ctx, chat_id=chat_id, callback_id=callback_id, scenario_id=sid
    )
    if scenario is None:
        return
    bank = scenario.pre_test if phase == "pre" else scenario.post_test
    if q_idx >= len(bank):
        await client.answer_callback(callback_id, notification="Вопрос уже завершён")
        return
    correct = choice == bank[q_idx].correct
    if phase == "pre":
        state = await ctx.state.answer_pre(user_id, correct=correct, total_questions=len(bank))
    else:
        state = await ctx.state.answer_post(user_id, correct=correct, total_questions=len(bank))
    if state is None:
        await client.answer_callback(callback_id, notification="Сначала открой сценарий")
        return
    feedback = "✅ Верно" if correct else "❌ Неверно"
    await client.answer_callback(callback_id, notification=feedback)
    if state.phase == "steps":
        await client.send_message(
            chat_id,
            f"Pre-test: {state.pre_correct}/{state.pre_total}. Поехали по шагам ⬇",
        )
        await _show_step(client, scenario, chat_id, state)
        return
    if state.phase == "done":
        await ctx.state.finish(user_id)
        await _award_xp_and_certificate(
            client,
            ctx,
            chat_id=chat_id,
            user_id=user_id,
            scenario_id=scenario.id,
            post_correct=state.post_correct,
            post_total=state.post_total,
        )
        return
    # ещё остались вопросы — показать следующий
    await _show_test_question(client, scenario, chat_id, phase, state.q_idx)


async def handle_callback(
    client: MaxBotClient,
    ctx: MaxAppContext,
    *,
    chat_id: int,
    user_id: int,
    callback_id: str,
    payload: str,
) -> None:
    if payload.startswith(CB_CAT_PREFIX):
        await _handle_category(client, ctx, chat_id, callback_id, payload)
        return
    if payload.startswith(CB_OPEN_PREFIX):
        await _handle_open(
            client, ctx, chat_id=chat_id, user_id=user_id, callback_id=callback_id, payload=payload
        )
        return
    if payload.startswith(CB_NEXT_PREFIX):
        await _handle_next(
            client, ctx, chat_id=chat_id, user_id=user_id, callback_id=callback_id, payload=payload
        )
        return
    if payload.startswith(CB_PREV_PREFIX):
        await _handle_prev(
            client, ctx, chat_id=chat_id, user_id=user_id, callback_id=callback_id, payload=payload
        )
        return
    if payload.startswith(CB_PRE_PREFIX):
        await _handle_test_answer(
            client,
            ctx,
            chat_id=chat_id,
            user_id=user_id,
            callback_id=callback_id,
            payload=payload,
            phase="pre",
        )
        return
    if payload.startswith(CB_POST_PREFIX):
        await _handle_test_answer(
            client,
            ctx,
            chat_id=chat_id,
            user_id=user_id,
            callback_id=callback_id,
            payload=payload,
            phase="post",
        )
        return
    if payload.startswith(CB_METRO_PREFIX):
        await client.send_message(chat_id, render_metronome_text())
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
    if payload == "cmd:profile":
        await handle_command(client, ctx, chat_id, user_id, "/profile")
        await client.answer_callback(callback_id)
        return
    if payload == "cmd:menu":
        await client.send_message(chat_id, WELCOME_TEXT, buttons=main_menu_buttons())
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


def extract_user_id(update: dict[str, Any]) -> int | None:
    """Достать ``user_id`` отправителя из любого типа апдейта Max."""
    msg = update.get("message")
    if msg and isinstance(msg, dict):
        sender = msg.get("sender") or {}
        if "user_id" in sender:
            return int(sender["user_id"])
    cb = update.get("callback")
    if cb and isinstance(cb, dict):
        user = cb.get("user") or {}
        if "user_id" in user:
            return int(user["user_id"])
    if "user_id" in update:
        return int(update["user_id"])
    return None


async def dispatch_update(client: MaxBotClient, ctx: MaxAppContext, update: dict[str, Any]) -> None:
    """Маршрутизация одного апдейта."""
    update_type = update.get("update_type") or update.get("type")
    chat_id = extract_chat_id(update)
    user_id = extract_user_id(update) or chat_id
    if update_type == "message_created":
        message = update.get("message") or {}
        body = (message.get("body") or {}).get("text", "")
        if not body or chat_id is None or user_id is None:
            return
        await handle_command(client, ctx, chat_id, user_id, body)
        return
    if update_type == "message_callback":
        cb = update.get("callback") or {}
        payload = cb.get("payload", "")
        callback_id = cb.get("callback_id", "")
        if not callback_id or chat_id is None or user_id is None:
            return
        await handle_callback(
            client,
            ctx,
            chat_id=chat_id,
            user_id=user_id,
            callback_id=callback_id,
            payload=payload,
        )
        return
    if update_type in ("bot_started", "bot_added"):
        if chat_id is not None:
            await client.send_message(chat_id, WELCOME_TEXT, buttons=main_menu_buttons())
        return
    log.debug("Игнорируем тип апдейта: %s", update_type)


# Backwards-compatibility: exported helper still referenced by tests.
__all__ = [
    "ACHIEVEMENTS",
    "MaxAppContext",
    "build_context",
    "category_buttons",
    "dispatch_update",
    "extract_chat_id",
    "extract_user_id",
    "handle_callback",
    "handle_command",
    "main_menu_buttons",
    "render_aed_list",
    "render_dispatcher_intro",
    "render_metronome_text",
    "render_panic_intro",
    "render_scenario_intro",
    "render_step",
    "render_test_question",
    "step_buttons",
    "test_buttons",
]
