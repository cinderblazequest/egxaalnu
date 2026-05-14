"""Telegram-обработчики СПАС-бота."""

from __future__ import annotations

import datetime as _dt
import logging
import os
from pathlib import Path

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Location,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.accessibility import render as a11y_render
from bot.aed import nearest
from bot.catalogue import Catalogue, Scenario
from bot.certificate import (
    CertificatePayload,
    build_certificate_code,
    save_certificate_png,
)
from bot.dispatcher import (
    DispatcherChecklist,
    load_dispatcher_checklist,
    render_summary,
)
from bot.gamification import evaluate_event, render_profile
from bot.i18n import SUPPORTED as SUPPORTED_LANGS
from bot.i18n import normalize_lang, t
from bot.llm import ask_llm
from bot.mchs_rss import known_regions
from bot.metronome import send_audio_metronome, send_text_metronome
from bot.panic import (
    back_to_panic_kb,
    find_triage,
    load_panic_protocol,
    panic_intro_kb,
    run_breathing,
    triage_kb,
)
from bot.sharing import (
    share_certificate_text,
    share_progress_text,
    telegram_share_url,
)
from bot.sos import render_sos_message
from bot.storage import Storage
from bot.stt import stt_enabled, transcribe_ogg
from bot.teacher import JoinClassState, TeacherState, render_class_progress, teacher_classes_kb
from bot.vision import triage_photo, vision_enabled

log = logging.getLogger("spas.handlers")


CERTIFICATE_THRESHOLD = 3
# Bump this when the privacy policy text materially changes — users will
# be re-asked to consent on next /start.
CONSENT_VERSION = "v1.2026"


class ScenarioState(StatesGroup):
    pre_test = State()
    in_steps = State()
    post_test = State()
    nps = State()


class DispatcherState(StatesGroup):
    answering = State()


class AedSubmitState(StatesGroup):
    waiting_location = State()
    waiting_name = State()
    waiting_photo = State()


class CertificateState(StatesGroup):
    waiting_name = State()


class SOSContactState(StatesGroup):
    waiting_contact = State()
    waiting_share_location = State()


SOS_TEXT = (
    "🆘 <b>SOS</b>\n\n"
    "1. Позвони <b>112</b> — единый номер спасения.\n"
    "2. Назови адрес, что случилось, сколько пострадавших.\n"
    "3. Не клади трубку — диспетчер подскажет.\n\n"
    "Что произошло? Выбери ситуацию ниже."
)


def sos_text(lang: str = "ru") -> str:
    """Localized SOS top-of-funnel instruction."""
    return t("sos.text", lang)


def main_menu_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t("menu.btn_sos", lang), callback_data="menu:sos")],
        [InlineKeyboardButton(text=t("menu.btn_panic", lang), callback_data="menu:panic")],
        [InlineKeyboardButton(text=t("menu.btn_critical", lang), callback_data="menu:critical")],
        [InlineKeyboardButton(text=t("menu.btn_urgent", lang), callback_data="menu:urgent")],
        [InlineKeyboardButton(text=t("menu.btn_minor", lang), callback_data="menu:minor")],
        [InlineKeyboardButton(text=t("menu.btn_training", lang), callback_data="menu:training")],
        [InlineKeyboardButton(text=t("menu.btn_aed", lang), callback_data="menu:aed")],
        [InlineKeyboardButton(text=t("menu.btn_add_aed", lang), callback_data="menu:add_aed")],
        [InlineKeyboardButton(text=t("menu.btn_dispatcher", lang), callback_data="menu:dispatcher")],
        [InlineKeyboardButton(text=t("menu.btn_certificate", lang), callback_data="menu:certificate")],
        [InlineKeyboardButton(text=t("menu.btn_profile", lang), callback_data="menu:profile")],
        [InlineKeyboardButton(text=t("menu.btn_ask", lang), callback_data="menu:ask")],
        [InlineKeyboardButton(text=t("menu.btn_feedback", lang), callback_data="menu:nps")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_kb(scenarios: list[Scenario], _category: str, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{s.icon} {s.title}", callback_data=f"scn:{s.id}")] for s in scenarios
    ]
    rows.append([InlineKeyboardButton(text=t("nav.back", lang), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def location_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def step_kb(
    scenario_id: str,
    idx: int,
    total: int,
    phone: str,
    lang: str = "ru",
    *,
    training: bool = False,
) -> InlineKeyboardMarkup:
    # Telegram inline keyboards do not allow tel:// URLs.
    # The phone number is rendered in the step text instead, where Telegram
    # mobile clients auto-detect it as a tappable link.
    _ = phone
    rows = []
    nav: list[InlineKeyboardButton] = []
    if idx > 0:
        nav.append(
            InlineKeyboardButton(text=t("step.back", lang), callback_data=f"step:{scenario_id}:{idx-1}")
        )
    if idx < total - 1:
        nav.append(
            InlineKeyboardButton(text=t("step.fwd", lang), callback_data=f"step:{scenario_id}:{idx+1}")
        )
    if nav:
        rows.append(nav)
    if idx == total - 1:
        finish_key = "step.finish_train" if training else "step.finish"
        rows.append([InlineKeyboardButton(text=t(finish_key, lang), callback_data=f"end:{scenario_id}")])
    rows.append([InlineKeyboardButton(text=t("step.metro", lang), callback_data=f"metro:{scenario_id}")])
    rows.append([InlineKeyboardButton(text=t("step.menu", lang), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def test_kb(scenario_id: str, phase: str, q_idx: int, options: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=opt, callback_data=f"ans:{scenario_id}:{phase}:{q_idx}:{i}")]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nps_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=str(i), callback_data=f"nps:{i}") for i in range(0, 6)],
        [InlineKeyboardButton(text=str(i), callback_data=f"nps:{i}") for i in range(6, 11)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dispatcher_question_kb(
    checklist: DispatcherChecklist, q_idx: int, lang: str = "ru"
) -> InlineKeyboardMarkup:
    q = checklist.questions[q_idx]
    rows = [
        [InlineKeyboardButton(text=ex[:60], callback_data=f"disp_e:{q_idx}:{i}")]
        for i, ex in enumerate(q.examples)
    ]
    rows.append([InlineKeyboardButton(text=t("disp.cancel", lang), callback_data="disp:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def aed_skip_photo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить фото", callback_data="aed_sub:skip")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="aed_sub:cancel")],
        ]
    )


def register_handlers(dp: Dispatcher, *, storage: Storage, content_dir: Path) -> None:
    catalogue = Catalogue(content_dir)
    panic_protocol = load_panic_protocol(content_dir)
    dispatcher_checklist = load_dispatcher_checklist(content_dir)

    async def _say(message: Message, html: str, **kwargs: object) -> Message:
        """Send a reply, applying user's accessibility preference."""
        a11y = False
        if message.from_user:
            settings = await storage.get_user_settings(message.from_user.id)
            a11y = bool(settings.get("accessibility"))
        return await message.answer(a11y_render(html, accessibility=a11y), **kwargs)  # type: ignore[arg-type]

    async def _grant_xp(
        user_id: int,
        event: str,
        *,
        perfect_post: bool = False,
    ) -> tuple[int, list[str]] | None:
        """Apply XP for an event; returns (xp_gained, new_achievement_titles) if changed."""
        try:
            state = await storage.get_xp(user_id)
            completed_count = await storage.count_distinct_completed_scenarios(user_id)
            completed_set = {f"_{i}" for i in range(completed_count)}
            delta = evaluate_event(
                state=state,
                event=event,
                completed_scenarios=completed_set,
                perfect_post=perfect_post,
            )
            new_xp = int(state.get("xp", 0)) + delta.xp_gained
            await storage.save_xp(
                user_id,
                xp=new_xp,
                level=delta.new_level,
                achievements=list(state.get("achievements", [])) + [a.code for a in delta.new_achievements],
                streak_days=delta.streak_days,
                last_active=_dt.datetime.now(_dt.UTC).isoformat(),
            )
            titles = [a.title for a in delta.new_achievements]
            return delta.xp_gained, titles
        except Exception as exc:
            log.warning("grant_xp(%s, %s) failed: %s", user_id, event, exc)
            return None

    async def _maybe_celebrate(message: Message, grant: tuple[int, list[str]] | None) -> None:
        if grant is None:
            return
        gained, titles = grant
        if gained <= 0 and not titles:
            return
        parts: list[str] = []
        if gained > 0:
            parts.append(f"+{gained} XP")
        if titles:
            ach_lines = "\n".join(f"🏅 <b>{t_}</b>" for t_ in titles)
            parts.append(f"Новые ачивки:\n{ach_lines}")
        await _say(message, "\n\n".join(parts))

    def _consent_kb(lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("consent.btn_accept", lang), callback_data="consent:accept")],
                [InlineKeyboardButton(text=t("consent.btn_privacy", lang), callback_data="consent:privacy")],
                [InlineKeyboardButton(text=t("consent.btn_decline", lang), callback_data="consent:decline")],
            ]
        )

    async def _start(message: Message, state: FSMContext) -> None:
        await state.clear()
        u = message.from_user
        if u:
            await storage.upsert_user(u.id, u.username)
            await storage.log_event(u.id, "start")
            settings = await storage.get_user_settings(u.id)
            lang = normalize_lang(settings.get("language", "ru"))
            if not await storage.has_consented(u.id, version=CONSENT_VERSION):
                await message.answer(t("consent.intro", lang), reply_markup=_consent_kb(lang))
                return
            await message.answer(t("menu.welcome", lang), reply_markup=main_menu_kb(lang))
            return
        await message.answer(t("menu.welcome", "ru"), reply_markup=main_menu_kb("ru"))

    dp.message.register(_start, CommandStart())

    async def _consent_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.from_user:
            await cb.answer()
            return
        action = cb.data.split(":", 1)[1]
        s = await storage.get_user_settings(cb.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        if action == "accept":
            await storage.record_consent(cb.from_user.id, version=CONSENT_VERSION)
            await storage.audit(
                "consent_accept",
                actor_id=cb.from_user.id,
                target=str(cb.from_user.id),
                details=CONSENT_VERSION,
            )
            if isinstance(cb.message, Message):
                await cb.message.edit_text(t("consent.accepted", lang))
        elif action == "decline":
            await storage.audit(
                "consent_decline",
                actor_id=cb.from_user.id,
                target=str(cb.from_user.id),
                details=CONSENT_VERSION,
            )
            if isinstance(cb.message, Message):
                await cb.message.edit_text(t("consent.declined", lang))
        elif action == "privacy":
            if isinstance(cb.message, Message):
                await cb.message.edit_text(t("consent.privacy", lang), reply_markup=_consent_kb(lang))
        await cb.answer()

    dp.callback_query.register(_consent_cb, F.data.startswith("consent:"))

    async def _privacy_cmd(message: Message) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        await message.answer(t("consent.privacy", lang))

    dp.message.register(_privacy_cmd, Command("privacy"))

    # ---- /forget_me (152-ФЗ H3) -----------------------------------------

    async def _forget_me_cmd(message: Message) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("forget.btn_yes", lang), callback_data="forget:yes")],
                [InlineKeyboardButton(text=t("forget.btn_no", lang), callback_data="forget:no")],
            ]
        )
        await message.answer(t("forget.confirm", lang), reply_markup=kb)

    dp.message.register(_forget_me_cmd, Command("forget_me"))

    async def _forget_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.from_user:
            await cb.answer()
            return
        decision = cb.data.split(":", 1)[1]
        s = await storage.get_user_settings(cb.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        if decision == "yes":
            stats = await storage.forget_user(cb.from_user.id)
            await storage.audit(
                "forget_me",
                actor_id=cb.from_user.id,
                target=str(cb.from_user.id),
                details=",".join(f"{k}={v}" for k, v in stats.items() if v),
            )
            if isinstance(cb.message, Message):
                await cb.message.edit_text(t("forget.done", lang))
        elif isinstance(cb.message, Message):
            await cb.message.edit_text(t("forget.cancelled", lang))
        await cb.answer()

    dp.callback_query.register(_forget_cb, F.data.startswith("forget:"))

    async def _sos(message: Message, state: FSMContext) -> None:
        await state.clear()
        if message.from_user:
            await storage.log_event(message.from_user.id, "sos")
            lang = await _user_lang(message.from_user.id)
        else:
            lang = "ru"
        await message.answer(
            t("sos.text", lang),
            reply_markup=category_kb(catalogue.list_critical(), "critical", lang),
        )

    dp.message.register(_sos, Command("sos"))

    async def _help(message: Message) -> None:
        text = (
            "Команды:\n"
            "/start — главное меню\n"
            "/sos — экстренная помощь\n"
            "/panic — мне страшно, подышим вместе\n"
            "/aed — найти АНД рядом\n"
            "/add_aed — добавить АНД на карту\n"
            "/dispatcher — что сказать диспетчеру 112\n"
            "/certificate — мой сертификат участника\n"
            "/profile — мой XP и ачивки\n"
            "/leaderboard — топ-10\n"
            "/setup_sos — задать доверенный контакт\n"
            "/sos_share — отправить SOS контакту с геолокацией\n"
            "/share_progress — поделиться прогрессом\n"
            "/share_certificate — поделиться сертификатом\n"
            "/teacher — открыть учительский режим\n"
            "/teacher_dashboard — мои классы\n"
            "/join CODE — присоединиться к классу\n"
            "/subscribe_alerts &lt;регион&gt; — алерты МЧС\n"
            "/unsubscribe_alerts — отписаться от алертов\n"
            "/my_alerts — список моих подписок\n"
            "/accessibility — крупный текст без эмодзи\n"
            "/lang — поменять язык (ru/en/uz/kk)\n"
            "/privacy — политика обработки данных\n"
            "/forget_me — удалить все мои данные (152-ФЗ)\n"
            "/ask — свободный вопрос AI\n"
            "/feedback — оценить бот\n\n"
            "Также можно прислать <b>фото раны/ожога</b> — я подскажу сценарий.\n\n"
            "Если в опасной ситуации — звони 112."
        )
        await message.answer(text)

    dp.message.register(_help, Command("help"))

    async def _panic_cmd(message: Message, state: FSMContext) -> None:
        await state.clear()
        if message.from_user:
            await storage.log_event(message.from_user.id, "panic_open")
            lang = await _user_lang(message.from_user.id)
        else:
            lang = "ru"
        await message.answer(
            f"😌 <b>Я рядом.</b>\n\n{panic_protocol.intro}",
            reply_markup=panic_intro_kb(lang),
        )

    dp.message.register(_panic_cmd, Command("panic"))

    async def _panic_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        target = cb.message
        action = cb.data.split(":", 1)[1]
        lang = await _user_lang(cb.from_user.id)
        if action == "home":
            await target.edit_text(
                f"😌 <b>Panic-режим.</b>\n\n{panic_protocol.intro}",
                reply_markup=panic_intro_kb(lang),
            )
        elif action == "breathe":
            await storage.log_event(cb.from_user.id, "panic_breathe")
            await target.edit_text(
                "Запускаю дыхание 6/мин. Считай со мной.",
                reply_markup=back_to_panic_kb(lang),
            )
            if cb.bot is not None:
                await run_breathing(cb.bot, target.chat.id, panic_protocol, lang=lang)
            grant = await _grant_xp(cb.from_user.id, "panic_breathe")
            await _maybe_celebrate(target, grant)
        elif action == "ground":
            await storage.log_event(cb.from_user.id, "panic_ground")
            lines = [panic_protocol.grounding_title]
            for i, line in enumerate(panic_protocol.grounding_lines, start=1):
                lines.append(f"{i}. {line}")
            lines.append("")
            lines.append(panic_protocol.grounding_outro)
            await target.edit_text("\n".join(lines), reply_markup=back_to_panic_kb(lang))
        elif action == "triage":
            await storage.log_event(cb.from_user.id, "panic_triage")
            await target.edit_text(
                "Что случилось? Выбери ближе по описанию.",
                reply_markup=triage_kb(panic_protocol, lang),
            )
        await cb.answer()
        _ = state

    dp.callback_query.register(_panic_cb, F.data.startswith("panic:"))

    async def _panic_triage_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        option_id = cb.data.split(":", 1)[1]
        opt = find_triage(panic_protocol, option_id)
        if not opt:
            await cb.answer("Не найдено")
            return
        await storage.log_event(cb.from_user.id, "panic_triage_pick", option_id)
        lang = await _user_lang(cb.from_user.id)
        rows: list[list[InlineKeyboardButton]] = []
        if opt.scenario:
            rows.append([InlineKeyboardButton(text="Открыть сценарий", callback_data=f"scn:{opt.scenario}")])
        rows.append([InlineKeyboardButton(text=t("panic.btn_panic_menu", lang), callback_data="panic:home")])
        rows.append([InlineKeyboardButton(text=t("step.menu", lang), callback_data="menu:home")])
        await cb.message.edit_text(opt.message, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await cb.answer()

    dp.callback_query.register(_panic_triage_cb, F.data.startswith("panic_t:"))

    async def _ask_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(ScenarioState.in_steps)
        await message.answer(
            "Напиши свой вопрос одним сообщением. Я отвечу коротко и подскажу нужный сценарий из меню.",
            reply_markup=ReplyKeyboardRemove(),
        )

    dp.message.register(_ask_cmd, Command("ask"))

    async def _feedback_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(ScenarioState.nps)
        await message.answer(
            "Насколько вероятно, что ты порекомендуешь СПАС друзьям? (0–10)",
            reply_markup=nps_kb(),
        )

    dp.message.register(_feedback_cmd, Command("feedback"))

    async def _aed_cmd(message: Message) -> None:
        await message.answer("Отправь геолокацию — я найду ближайший АНД.", reply_markup=location_kb())

    dp.message.register(_aed_cmd, Command("aed"))

    async def _add_aed_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(AedSubmitState.waiting_location)
        await message.answer(
            "Спасибо, что хочешь дополнить базу АНД!\n\n"
            "1. Пришли геолокацию точки (можно «отправить выбранное место»).",
            reply_markup=location_kb(),
        )

    dp.message.register(_add_aed_cmd, Command("add_aed"))

    async def _dispatcher_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(DispatcherState.answering)
        await state.update_data(answers={}, q_idx=0)
        if message.from_user:
            await storage.log_event(message.from_user.id, "dispatcher_open")
            lang = await _user_lang(message.from_user.id)
        else:
            lang = "ru"
        first = dispatcher_checklist.questions[0]
        await message.answer(
            f"{dispatcher_checklist.intro}\n\n<b>{first.label}</b>\n<i>{first.hint}</i>",
            reply_markup=dispatcher_question_kb(dispatcher_checklist, 0, lang),
        )

    dp.message.register(_dispatcher_cmd, Command("dispatcher"))

    async def _certificate_cmd(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        completed = await storage.count_distinct_completed_scenarios(message.from_user.id)
        if completed < CERTIFICATE_THRESHOLD:
            await message.answer(
                f"🎓 Сертификат выдаётся после {CERTIFICATE_THRESHOLD} завершённых сценариев.\n"
                f"Ты прошёл(ла) {completed}. Открой ещё немного: /start",
            )
            return
        await state.set_state(CertificateState.waiting_name)
        await state.update_data(scenarios_completed=completed)
        await message.answer(
            "🎓 <b>Сертификат участника пилота СПАС</b>\n\n"
            f"Ты прошёл(ла) <b>{completed}</b> сценариев. Это внутренний знак "
            "участия, не медицинский документ.\n\n"
            "Напиши, как тебя зовут (Имя Фамилия) — впишу в сертификат.",
            reply_markup=ReplyKeyboardRemove(),
        )

    dp.message.register(_certificate_cmd, Command("certificate"))

    async def _location(message: Message, state: FSMContext) -> None:
        loc: Location | None = message.location
        if not loc or not message.from_user:
            return
        cur_state = await state.get_state()
        if cur_state == AedSubmitState.waiting_location.state:
            await state.update_data(lat=loc.latitude, lon=loc.longitude)
            await state.set_state(AedSubmitState.waiting_name)
            await message.answer(
                "Геолокация получена. 2. Где это? Напиши коротко: <b>город — название места</b>.\n"
                "Пример: <i>Москва — ТРЦ Авиапарк, 1 этаж у входа</i>.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        hits = nearest(loc.latitude, loc.longitude, catalogue.aed, k=3)
        if not hits:
            await message.answer(
                "База АНД пока пустая. Спасибо, что попробовал — мы её скоро дополним.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        lines = ["📍 <b>Ближайшие АНД:</b>"]
        for h in hits:
            lines.append(
                f"\n• <b>{h.location.name}</b>\n  {h.location.city}, {h.distance_km:.1f} км\n  {h.location.note}"
            )
        await message.answer("\n".join(lines), reply_markup=ReplyKeyboardRemove())
        await storage.log_event(message.from_user.id, "aed_lookup")

    dp.message.register(_location, F.location)

    async def _aed_name(message: Message, state: FSMContext) -> None:
        if not message.text or not message.from_user:
            return
        await state.update_data(name=message.text.strip()[:200])
        await state.set_state(AedSubmitState.waiting_photo)
        await message.answer(
            "3. Прикрепи фото устройства (или нажми «Пропустить фото» — модератор сможет проверить точку по карте).",
            reply_markup=aed_skip_photo_kb(),
        )

    dp.message.register(_aed_name, AedSubmitState.waiting_name, F.text)

    async def _save_aed_submission(
        sender: Message | CallbackQuery,
        state: FSMContext,
        photo_file_id: str | None,
    ) -> None:
        data = await state.get_data()
        from_user = sender.from_user
        if not from_user:
            return
        name_value = data.get("name", "")
        if isinstance(name_value, str) and "—" in name_value:
            city_part, _, rest = name_value.partition("—")
            city = city_part.strip()[:60]
            name = rest.strip()[:200]
        else:
            city = None
            name = (name_value if isinstance(name_value, str) else "")[:200]
        sub_id = await storage.insert_aed_submission(
            user_id=from_user.id,
            city=city,
            name=name,
            note=None,
            lat=float(data.get("lat", 0.0)),
            lon=float(data.get("lon", 0.0)),
            photo_file_id=photo_file_id,
        )
        await storage.log_event(from_user.id, "aed_submission", str(sub_id))
        await state.clear()
        text = (
            "🙏 Спасибо! Заявка отправлена на модерацию (обычно — до 48 часов).\n"
            "Когда точку подтвердят, она появится в /aed для всех."
        )
        if isinstance(sender, CallbackQuery) and isinstance(sender.message, Message):
            await sender.message.answer(text, reply_markup=main_menu_kb())
        elif isinstance(sender, Message):
            await sender.answer(text, reply_markup=main_menu_kb())

    async def _aed_photo(message: Message, state: FSMContext) -> None:
        if not message.photo or not message.from_user:
            return
        await _save_aed_submission(message, state, message.photo[-1].file_id)

    dp.message.register(_aed_photo, AedSubmitState.waiting_photo, F.photo)

    async def _aed_sub_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        action = cb.data.split(":", 1)[1]
        if action == "cancel":
            await state.clear()
            if isinstance(cb.message, Message):
                await cb.message.answer("Отменено.", reply_markup=main_menu_kb())
        elif action == "skip":
            await _save_aed_submission(cb, state, None)
        await cb.answer()

    dp.callback_query.register(_aed_sub_cb, F.data.startswith("aed_sub:"))

    async def _certificate_name_received(message: Message, state: FSMContext) -> None:
        if not message.text or not message.from_user:
            return
        full_name = message.text.strip()[:80]
        if not full_name:
            await message.answer("Имя не должно быть пустым. Попробуй ещё раз.")
            return
        data = await state.get_data()
        scenarios_completed = int(data.get("scenarios_completed", CERTIFICATE_THRESHOLD))
        issued_at = _dt.datetime.now(_dt.UTC)
        code = build_certificate_code(message.from_user.id, scenarios_completed, issued_at)
        payload = CertificatePayload(
            user_id=message.from_user.id,
            full_name=full_name,
            scenarios_completed=scenarios_completed,
            issued_at=issued_at,
            code=code,
        )
        png = save_certificate_png(payload)
        await storage.save_certificate(message.from_user.id, code, full_name, scenarios_completed)
        await storage.log_event(message.from_user.id, "certificate_issued", code)
        await message.answer_document(
            BufferedInputFile(png, filename=f"spas_certificate_{code}.png"),
            caption=(
                f"🎓 Готово, <b>{full_name}</b>!\n"
                f"Код сертификата: <code>{code}</code>\n\n"
                "Это внутренний знак участия в пилоте СПАС, не официальный мед.документ."
            ),
        )
        await state.clear()
        await message.answer("Что дальше?", reply_markup=main_menu_kb())

    dp.message.register(_certificate_name_received, CertificateState.waiting_name, F.text)

    async def _dispatcher_advance(
        sender: Message | CallbackQuery,
        state: FSMContext,
        answers: dict[str, str],
        next_idx: int,
    ) -> None:
        if next_idx >= len(dispatcher_checklist.questions):
            text = render_summary(dispatcher_checklist, answers)
            target_msg: Message | None = None
            if isinstance(sender, CallbackQuery) and isinstance(sender.message, Message):
                await sender.message.answer(text, reply_markup=main_menu_kb())
                target_msg = sender.message
            elif isinstance(sender, Message):
                await sender.answer(text, reply_markup=main_menu_kb())
                target_msg = sender
            if sender.from_user:
                await storage.log_event(sender.from_user.id, "dispatcher_done")
                if target_msg is not None:
                    grant = await _grant_xp(sender.from_user.id, "dispatcher_done")
                    await _maybe_celebrate(target_msg, grant)
            await state.clear()
            return
        await state.update_data(answers=answers, q_idx=next_idx)
        q = dispatcher_checklist.questions[next_idx]
        text = f"<b>{q.label}</b>\n<i>{q.hint}</i>"
        uid = sender.from_user.id if sender.from_user else None
        lang = await _user_lang(uid) if uid is not None else "ru"
        kb = dispatcher_question_kb(dispatcher_checklist, next_idx, lang)
        if isinstance(sender, CallbackQuery) and isinstance(sender.message, Message):
            await sender.message.answer(text, reply_markup=kb)
        elif isinstance(sender, Message):
            await sender.answer(text, reply_markup=kb)

    async def _dispatcher_text(message: Message, state: FSMContext) -> None:
        if not message.text or not message.from_user:
            return
        data = await state.get_data()
        q_idx = int(data.get("q_idx", 0))
        answers = dict(data.get("answers", {}))
        q = dispatcher_checklist.questions[q_idx]
        answers[q.id] = message.text.strip()[:300]
        await _dispatcher_advance(message, state, answers, q_idx + 1)

    dp.message.register(_dispatcher_text, DispatcherState.answering, F.text)

    async def _dispatcher_example_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        _, q_idx_s, ex_idx_s = cb.data.split(":")
        q_idx = int(q_idx_s)
        data = await state.get_data()
        answers = dict(data.get("answers", {}))
        q = dispatcher_checklist.questions[q_idx]
        answers[q.id] = q.examples[int(ex_idx_s)]
        await _dispatcher_advance(cb, state, answers, q_idx + 1)
        await cb.answer()

    dp.callback_query.register(_dispatcher_example_cb, F.data.startswith("disp_e:"))

    async def _dispatcher_cancel_cb(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        if isinstance(cb.message, Message):
            await cb.message.answer("Прервал. /start — главное меню.", reply_markup=main_menu_kb())
        await cb.answer()

    dp.callback_query.register(_dispatcher_cancel_cb, F.data == "disp:cancel")

    async def _free_text(message: Message, state: FSMContext) -> None:
        if not message.text or not message.from_user:
            return
        await storage.log_event(message.from_user.id, "ask", message.text[:200])
        await message.answer("Думаю…")
        answer = await ask_llm(message.text)
        if not answer:
            answer = (
                "Свободные вопросы пока не подключены (нужен ключ GigaChat / YandexGPT).\n"
                "Попробуй выбрать сценарий из меню — там пошаговый алгоритм."
            )
        await message.answer(answer, reply_markup=main_menu_kb())
        await state.clear()

    dp.message.register(_free_text, ScenarioState.in_steps, F.text)

    async def _menu_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        action = cb.data.split(":", 1)[1]
        target = cb.message
        settings = await storage.get_user_settings(cb.from_user.id)
        lang = normalize_lang(settings.get("language", "ru"))
        if action == "home":
            await state.update_data(training=False)
            await target.edit_text(t("menu.welcome", lang), reply_markup=main_menu_kb(lang))
        elif action == "training":
            await state.update_data(training=True)
            scenarios_with_test = [sc for sc in catalogue.scenarios.values() if sc.pre_test or sc.post_test]
            if not scenarios_with_test:
                await target.edit_text(t("menu.training_empty", lang), reply_markup=main_menu_kb(lang))
            else:
                rows = [
                    [InlineKeyboardButton(text=f"{sc.icon} {sc.title}", callback_data=f"tscn:{sc.id}")]
                    for sc in scenarios_with_test
                ]
                rows.append([InlineKeyboardButton(text=t("step.menu", lang), callback_data="menu:home")])
                await target.edit_text(
                    t("menu.training_intro", lang),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                )
            await storage.log_event(cb.from_user.id, "training_menu")
        elif action == "sos":
            await target.edit_text(
                t("sos.text", lang),
                reply_markup=category_kb(catalogue.list_critical(), "critical", lang),
            )
        elif action == "panic":
            await storage.log_event(cb.from_user.id, "panic_open")
            await target.edit_text(
                f"😌 <b>Я рядом.</b>\n\n{panic_protocol.intro}",
                reply_markup=panic_intro_kb(lang),
            )
        elif action == "critical":
            await target.edit_text(
                t("cat.critical", lang),
                reply_markup=category_kb(catalogue.list_critical(), "critical", lang),
            )
        elif action == "urgent":
            await target.edit_text(
                t("cat.urgent", lang),
                reply_markup=category_kb(catalogue.list_urgent(), "urgent", lang),
            )
        elif action == "minor":
            await target.edit_text(
                t("cat.minor", lang),
                reply_markup=category_kb(catalogue.list_minor(), "minor", lang),
            )
        elif action == "aed":
            await target.answer("Отправь геолокацию ниже:", reply_markup=location_kb())
        elif action == "add_aed":
            await state.set_state(AedSubmitState.waiting_location)
            await target.answer(
                "1. Пришли геолокацию точки (можно «отправить выбранное место»).",
                reply_markup=location_kb(),
            )
        elif action == "dispatcher":
            await state.set_state(DispatcherState.answering)
            await state.update_data(answers={}, q_idx=0)
            await storage.log_event(cb.from_user.id, "dispatcher_open")
            first = dispatcher_checklist.questions[0]
            await target.answer(
                f"{dispatcher_checklist.intro}\n\n<b>{first.label}</b>\n<i>{first.hint}</i>",
                reply_markup=dispatcher_question_kb(dispatcher_checklist, 0, lang),
            )
        elif action == "certificate":
            completed = await storage.count_distinct_completed_scenarios(cb.from_user.id)
            if completed < CERTIFICATE_THRESHOLD:
                await target.answer(
                    f"🎓 Сертификат — после {CERTIFICATE_THRESHOLD} завершённых сценариев. "
                    f"Ты прошёл(ла) {completed}.",
                )
            else:
                await state.set_state(CertificateState.waiting_name)
                await state.update_data(scenarios_completed=completed)
                await target.answer(
                    "🎓 Напиши, как тебя зовут (Имя Фамилия) — впишу в сертификат.",
                    reply_markup=ReplyKeyboardRemove(),
                )
        elif action == "ask":
            await target.answer(
                "Напиши свой вопрос одним сообщением, я отвечу коротко.",
                reply_markup=ReplyKeyboardRemove(),
            )
        elif action == "profile":
            xp_state = await storage.get_xp(cb.from_user.id)
            await target.answer(render_profile(xp_state))
        elif action == "nps":
            await target.answer("Оцени от 0 до 10:", reply_markup=nps_kb())
        await cb.answer()

    dp.callback_query.register(_menu_cb, F.data.startswith("menu:"))

    async def _user_lang(uid: int) -> str:
        s = await storage.get_user_settings(uid)
        return normalize_lang(s.get("language", "ru"))

    async def _start_steps(
        cb: CallbackQuery, scenario: Scenario, idx: int, *, training: bool = False
    ) -> None:
        if not cb.message or not cb.from_user or not isinstance(cb.message, Message):
            return
        lang = await _user_lang(cb.from_user.id)
        text = (
            f"{scenario.icon} <b>{scenario.title}</b>\n"
            f"<i>{scenario.summary}</i>\n\n"
            f"📞 Экстренный: <code>{scenario.phone}</code>\n\n"
            f"<b>Шаг {idx + 1}/{len(scenario.steps)}</b>\n\n"
            f"{scenario.steps[idx]}"
        )
        await cb.message.edit_text(
            text,
            reply_markup=step_kb(
                scenario.id, idx, len(scenario.steps), scenario.phone, lang, training=training
            ),
        )

    async def _scenario_cb(cb: CallbackQuery, state: FSMContext) -> None:
        """Open a scenario directly with steps; pre-test is reserved for /training."""
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        scenario_id = cb.data.split(":", 1)[1]
        scenario = catalogue.scenarios.get(scenario_id)
        if not scenario:
            await cb.answer("Не найдено")
            return
        await state.update_data(training=False)
        await storage.log_event(cb.from_user.id, "scenario_open", scenario_id)
        await _start_steps(cb, scenario, 0, training=False)
        await cb.answer()

    dp.callback_query.register(_scenario_cb, F.data.startswith("scn:"))

    async def _training_scn_cb(cb: CallbackQuery, state: FSMContext) -> None:
        """Training mode: pre-test (if available) -> steps -> post-test."""
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        scenario_id = cb.data.split(":", 1)[1]
        scenario = catalogue.scenarios.get(scenario_id)
        if not scenario:
            await cb.answer("Не найдено")
            return
        await storage.log_event(cb.from_user.id, "training_open", scenario_id)
        await state.update_data(training=True)
        lang = await _user_lang(cb.from_user.id)
        if scenario.pre_test:
            await state.set_state(ScenarioState.pre_test)
            await state.update_data(
                scenario_id=scenario_id, phase="pre", correct=0, total=0, q_idx=0, training=True
            )
            q = scenario.pre_test[0]
            await cb.message.edit_text(
                t("scenario.training_pre", lang, question=q.q),
                reply_markup=test_kb(scenario_id, "pre", 0, q.options),
            )
        else:
            await _start_steps(cb, scenario, 0, training=True)
        await cb.answer()

    dp.callback_query.register(_training_scn_cb, F.data.startswith("tscn:"))

    async def _step_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        _, scenario_id, idx_s = cb.data.split(":")
        idx = int(idx_s)
        scenario = catalogue.scenarios.get(scenario_id)
        if not scenario:
            return
        await storage.log_event(cb.from_user.id, "step_open", f"{scenario_id}:{idx}")
        data = await state.get_data()
        training = bool(data.get("training", False))
        await _start_steps(cb, scenario, idx, training=training)
        await cb.answer()

    dp.callback_query.register(_step_cb, F.data.startswith("step:"))

    async def _metro_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message) or cb.bot is None:
            await cb.answer()
            return
        scenario_id = cb.data.split(":", 1)[1]
        await storage.log_event(cb.from_user.id, "metronome_play", scenario_id)
        await cb.answer("Запускаю метроном 110 BPM…")
        sent = await send_audio_metronome(cb.bot, cb.message.chat.id, bpm=110)
        if not sent:
            await send_text_metronome(cb.bot, cb.message.chat.id, bpm=110, seconds=15)

    dp.callback_query.register(_metro_cb, F.data.startswith("metro:"))

    async def _end_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        scenario_id = cb.data.split(":", 1)[1]
        await storage.log_event(cb.from_user.id, "scenario_complete", scenario_id)
        scenario = catalogue.scenarios.get(scenario_id)
        data = await state.get_data()
        training = bool(data.get("training", False))
        lang = await _user_lang(cb.from_user.id)
        if not scenario or not training or not scenario.post_test:
            await state.clear()
            await cb.message.answer(t("scenario.completed", lang), reply_markup=main_menu_kb(lang))
            await cb.answer()
            return
        await state.set_state(ScenarioState.post_test)
        await state.update_data(
            scenario_id=scenario_id, phase="post", correct=0, total=0, q_idx=0, training=True
        )
        q = scenario.post_test[0]
        await cb.message.answer(
            t("scenario.training_post", lang, question=q.q),
            reply_markup=test_kb(scenario_id, "post", 0, q.options),
        )
        await cb.answer()

    dp.callback_query.register(_end_cb, F.data.startswith("end:"))

    async def _ans_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.message or not cb.from_user:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        _, scenario_id, phase, q_idx_s, choice_s = cb.data.split(":")
        scenario = catalogue.scenarios.get(scenario_id)
        if not scenario:
            return
        q_idx = int(q_idx_s)
        choice = int(choice_s)
        bank = scenario.pre_test if phase == "pre" else scenario.post_test
        if not bank:
            return
        question = bank[q_idx]
        is_correct = choice == question.correct

        data = await state.get_data()
        correct_total = int(data.get("correct", 0)) + (1 if is_correct else 0)
        total = int(data.get("total", 0)) + 1
        await state.update_data(correct=correct_total, total=total)

        feedback = (
            "✅ Верно!" if is_correct else f"❌ Правильный ответ: <b>{question.options[question.correct]}</b>"
        )
        await cb.message.edit_text(
            f"{scenario.icon} <b>{scenario.title}</b>\n\nВопрос {q_idx + 1}: {question.q}\n\n{feedback}"
        )

        next_idx = q_idx + 1
        if next_idx < len(bank):
            next_q = bank[next_idx]
            await state.update_data(q_idx=next_idx)
            await cb.message.answer(
                f"<b>Вопрос {next_idx + 1}/{len(bank)}.</b>\n\n{next_q.q}",
                reply_markup=test_kb(scenario_id, phase, next_idx, next_q.options),
            )
            await cb.answer()
            return

        await storage.save_test(cb.from_user.id, scenario_id, phase, correct_total, total)
        training = bool(data.get("training", False))
        if phase == "pre":
            await state.set_state(ScenarioState.in_steps)
            await state.update_data(training=training)
            await cb.message.answer(
                f"📊 Результат до обучения: {correct_total}/{total}.\nТеперь — пошаговый алгоритм.",
            )
            await _start_steps(cb, scenario, 0, training=training)
        else:
            completed = await storage.count_distinct_completed_scenarios(cb.from_user.id)
            extra = ""
            if completed >= CERTIFICATE_THRESHOLD:
                extra = (
                    f"\n\n🎓 Ты прошёл(ла) <b>{completed}</b> сценариев — "
                    "можно забрать сертификат: /certificate"
                )
            await state.clear()
            await cb.message.answer(
                f"📊 Результат после обучения: {correct_total}/{total}.\n\n"
                f"Спасибо! Если хочешь — оцени бот: /feedback\n"
                f"Или открой ещё сценарий: /start" + extra
            )
        await cb.answer()

    dp.callback_query.register(_ans_cb, F.data.startswith("ans:"))

    async def _nps_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.data or not cb.from_user or not cb.message:
            return
        if not isinstance(cb.message, Message):
            await cb.answer()
            return
        score = int(cb.data.split(":", 1)[1])
        await storage.save_feedback(cb.from_user.id, score, None)
        await storage.log_event(cb.from_user.id, "nps", str(score))
        await cb.message.edit_text(
            f"Спасибо! Твоя оценка: <b>{score}/10</b>.\n"
            f"Если хочешь оставить комментарий — просто напиши его сообщением."
        )
        await state.clear()
        await cb.answer()

    dp.callback_query.register(_nps_cb, F.data.startswith("nps:"))

    admin_id_str = os.getenv("ADMIN_ID", "")
    admin_id = int(admin_id_str) if admin_id_str.isdigit() else None

    async def _stats(message: Message) -> None:
        if not message.from_user or message.from_user.id != admin_id:
            return
        m = await storage.metrics()
        await message.answer(
            "<b>📊 Метрики СПАС</b>\n\n"
            f"Пользователей всего: <b>{m['users_total']}</b>\n"
            f"DAU: <b>{m['dau']}</b>\n"
            f"Завершено сценариев: <b>{m['scenarios_completed']}</b>\n"
            f"Средний NPS: <b>{m['avg_nps']:.1f}</b>\n"
            f"Pre-test средний: <b>{(m['pre_score_avg'] or 0):.0%}</b>\n"
            f"Post-test средний: <b>{(m['post_score_avg'] or 0):.0%}</b>\n"
        )

    dp.message.register(_stats, Command("stats"))

    async def _aed_review(message: Message) -> None:
        if not message.from_user or message.from_user.id != admin_id:
            return
        pending = await storage.list_pending_aed()
        if not pending:
            await message.answer("Нет заявок на модерации.")
            return
        for p in pending[:10]:
            text = (
                f"#{p['id']} @{p['user_id']} | {p['ts']}\n"
                f"<b>{p['city'] or '-'}</b> — {p['name'] or '-'}\n"
                f"{p['lat']:.5f}, {p['lon']:.5f}\n"
                f"<a href=\"https://www.openstreetmap.org/?mlat={p['lat']}&mlon={p['lon']}"
                f"#map=18/{p['lat']}/{p['lon']}\">OpenStreetMap</a>"
            )
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Принять", callback_data=f"aed_mod:{p['id']}:approve"),
                        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"aed_mod:{p['id']}:reject"),
                    ]
                ]
            )
            if p["photo_file_id"]:
                await message.answer_photo(p["photo_file_id"], caption=text, reply_markup=kb)
            else:
                await message.answer(text, reply_markup=kb)

    dp.message.register(_aed_review, Command("aed_review"))

    async def _aed_mod_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.from_user or cb.from_user.id != admin_id:
            await cb.answer("Только для админа")
            return
        _, sub_id_s, action = cb.data.split(":")
        sub_id = int(sub_id_s)
        new_status = "approved" if action == "approve" else "rejected"
        await storage.update_aed_status(sub_id, new_status)
        await storage.audit(
            "aed_moderation",
            actor_id=cb.from_user.id,
            target=f"aed:{sub_id}",
            details=new_status,
        )
        await cb.answer(f"#{sub_id} → {new_status}")

    dp.callback_query.register(_aed_mod_cb, F.data.startswith("aed_mod:"))

    # ---- gamification: /profile, /leaderboard ----------------------------

    async def _profile_cmd(message: Message) -> None:
        if not message.from_user:
            return
        state_ = await storage.get_xp(message.from_user.id)
        await _say(message, render_profile(state_))

    dp.message.register(_profile_cmd, Command("profile"))

    async def _leaderboard_cmd(message: Message) -> None:
        rows = await storage.leaderboard(limit=10)
        if not rows:
            await _say(message, "Лидерборд пуст. Стань первым: /start")
            return
        lines = ["<b>🏆 Лидеры по XP</b>", ""]
        for i, r in enumerate(rows, start=1):
            handle = ("@" + r["username"]) if r["username"] else f"user_{r['user_id']}"
            lines.append(f"{i}. <b>{handle}</b> — Lv {r['level']} · {r['xp']} XP")
        await _say(message, "\n".join(lines))

    dp.message.register(_leaderboard_cmd, Command("leaderboard"))

    # ---- accessibility & language ----------------------------------------

    async def _accessibility_cmd(message: Message) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        new_value = not bool(s.get("accessibility"))
        await storage.set_user_setting(message.from_user.id, accessibility=new_value)
        lang = normalize_lang(s.get("language", "ru"))
        key = "a11y.on" if new_value else "a11y.off"
        await message.answer(t(key, lang))

    dp.message.register(_accessibility_cmd, Command("accessibility"))

    _LANG_BUTTONS = (
        ("ru", "🇷🇺 Русский"),
        ("en", "🇬🇧 English"),
        ("uz", "🇺🇿 O'zbekcha"),
        ("kk", "🇰🇿 Қазақша"),
    )

    async def _lang_cmd(message: Message, command: CommandObject) -> None:
        if not message.from_user:
            return
        arg = normalize_lang((command.args or "").strip().lower())
        raw = (command.args or "").strip().lower()
        if raw and raw in {*SUPPORTED_LANGS, "kz"}:
            await storage.set_user_setting(message.from_user.id, language=arg)
            await message.answer(t("lang.changed", arg))
            return
        rows = [
            [InlineKeyboardButton(text=label, callback_data=f"lang:{code}")] for code, label in _LANG_BUTTONS
        ]
        await message.answer(t("lang.choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    dp.message.register(_lang_cmd, Command("lang"))

    async def _lang_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.from_user:
            await cb.answer()
            return
        code = normalize_lang(cb.data.split(":", 1)[1])
        await storage.set_user_setting(cb.from_user.id, language=code)
        if isinstance(cb.message, Message):
            await cb.message.edit_text(t("lang.changed", code))
        await cb.answer()

    dp.callback_query.register(_lang_cb, F.data.startswith("lang:"))

    # ---- SOS: trusted contact + /sos_share with location -----------------

    async def _setup_sos_cmd(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        await state.set_state(SOSContactState.waiting_contact)
        await _say(
            message,
            "🆘 <b>Настройка доверенного контакта.</b>\n\n"
            "Перешли мне любое сообщение от того, кому я должен послать "
            "тревогу при /sos_share. Я запомню его chat_id (без сообщений, "
            "только сам контакт).",
        )

    dp.message.register(_setup_sos_cmd, Command("setup_sos"))

    async def _setup_sos_msg(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        forwarded_from = getattr(message, "forward_from", None)
        if not forwarded_from:
            await _say(
                message,
                "Это не похоже на пересланное сообщение. Перешли любое "
                "сообщение от доверенного контакта (если у него скрыто "
                "пересланное от — он скрыл это в настройках, попроси "
                "его временно включить).",
            )
            return
        display_name = f"{forwarded_from.first_name or ''} {forwarded_from.last_name or ''}".strip() or (
            f"@{forwarded_from.username}" if forwarded_from.username else "контакт"
        )
        await storage.set_sos_contact(
            message.from_user.id,
            contact_chat_id=forwarded_from.id,
            contact_username=forwarded_from.username,
            display_name=display_name[:80],
        )
        await state.clear()
        s = await storage.get_user_settings(message.from_user.id)
        await message.answer(t("sos.set_ok", s.get("language", "ru"), name=display_name))

    dp.message.register(_setup_sos_msg, SOSContactState.waiting_contact, F.forward_from)
    dp.message.register(_setup_sos_msg, SOSContactState.waiting_contact, F.text)

    async def _sos_clear_cmd(message: Message) -> None:
        if not message.from_user:
            return
        await storage.delete_sos_contact(message.from_user.id)
        s = await storage.get_user_settings(message.from_user.id)
        await message.answer(t("sos.cleared", s.get("language", "ru")))

    dp.message.register(_sos_clear_cmd, Command("sos_clear"))

    async def _sos_share_cmd(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        contact = await storage.get_sos_contact(message.from_user.id)
        s = await storage.get_user_settings(message.from_user.id)
        lang = s.get("language", "ru")
        if not contact or not contact.get("contact_chat_id"):
            await _say(message, t("sos.no_contact", lang))
            return
        await state.set_state(SOSContactState.waiting_share_location)
        await message.answer(t("sos.share_intro", lang), reply_markup=location_kb())

    dp.message.register(_sos_share_cmd, Command("sos_share"))

    async def _sos_share_location(message: Message, state: FSMContext) -> None:
        if not message.from_user or not message.location:
            return
        contact = await storage.get_sos_contact(message.from_user.id)
        if not contact or not contact.get("contact_chat_id"):
            await state.clear()
            await _say(message, "Доверенный контакт не задан.")
            return
        u = message.from_user
        full_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or (
            f"@{u.username}" if u.username else "пользователь СПАС"
        )
        text = render_sos_message(
            name=full_name,
            lat=message.location.latitude,
            lon=message.location.longitude,
            note=None,
        )
        delivered = False
        if message.bot is not None:
            try:
                await message.bot.send_message(
                    chat_id=int(contact["contact_chat_id"]), text=text, disable_web_page_preview=False
                )
                delivered = True
            except Exception as exc:
                log.warning("sos send failed: %s", exc)
        await state.clear()
        await storage.log_event(message.from_user.id, "sos_share", "ok" if delivered else "fail")
        if delivered:
            await message.answer(
                f"📨 Отправлено {contact.get('display_name') or 'контакту'}. " "Не забудь набрать 112.",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await message.answer(
                "❗ Не получилось отправить (контакт мог не открывать с тобой бота). "
                "Скопируй текст ниже и пришли вручную:\n\n" + text,
                reply_markup=ReplyKeyboardRemove(),
            )

    dp.message.register(_sos_share_location, SOSContactState.waiting_share_location, F.location)

    # ---- teacher mode: /teacher, /teacher_dashboard, /join ---------------

    async def _teacher_cmd(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = s.get("language", "ru")
        await state.set_state(TeacherState.naming)
        await message.answer(t("teacher.intro", lang) + "\n\n" + t("teacher.ask_name", lang))

    dp.message.register(_teacher_cmd, Command("teacher"))

    async def _teacher_name_text(message: Message, state: FSMContext) -> None:
        if not message.from_user or not message.text:
            return
        name = message.text.strip()
        if not name:
            await _say(message, "Имя не должно быть пустым.")
            return
        cls = await storage.create_class(message.from_user.id, name)
        s = await storage.get_user_settings(message.from_user.id)
        lang = s.get("language", "ru")
        await message.answer(t("teacher.created", lang, name=cls["name"], code=cls["invite_code"]))
        await state.clear()

    dp.message.register(_teacher_name_text, TeacherState.naming, F.text)

    async def _teacher_dashboard_cmd(message: Message) -> None:
        if not message.from_user:
            return
        classes = await storage.list_classes_by_teacher(message.from_user.id)
        s = await storage.get_user_settings(message.from_user.id)
        lang = s.get("language", "ru")
        if not classes:
            await message.answer(t("teacher.no_classes", lang))
            return
        await _say(message, "📋 Твои классы:", reply_markup=teacher_classes_kb(classes))

    dp.message.register(_teacher_dashboard_cmd, Command("teacher_dashboard"))

    async def _teacher_new_cb(cb: CallbackQuery, state: FSMContext) -> None:
        if not cb.from_user or not isinstance(cb.message, Message):
            await cb.answer()
            return
        await state.set_state(TeacherState.naming)
        s = await storage.get_user_settings(cb.from_user.id)
        await cb.message.answer(t("teacher.ask_name", s.get("language", "ru")))
        await cb.answer()

    dp.callback_query.register(_teacher_new_cb, F.data == "teacher:new")

    async def _teacher_view_cb(cb: CallbackQuery) -> None:
        if not cb.data or not cb.from_user or not isinstance(cb.message, Message):
            await cb.answer()
            return
        class_id = int(cb.data.split(":", 1)[1])
        classes = await storage.list_classes_by_teacher(cb.from_user.id)
        match = next((c for c in classes if c["id"] == class_id), None)
        if not match:
            await cb.answer("Класс не найден")
            return
        progress = await storage.class_progress(class_id)
        await cb.message.answer(render_class_progress(match, progress))
        await cb.answer()

    dp.callback_query.register(_teacher_view_cb, F.data.startswith("teacher_view:"))

    async def _join_cmd(message: Message, state: FSMContext, command: CommandObject) -> None:
        if not message.from_user:
            return
        code = (command.args or "").strip().upper()
        s = await storage.get_user_settings(message.from_user.id)
        lang = s.get("language", "ru")
        if not code:
            await message.answer("Использование: <code>/join CODE</code>")
            return
        cls = await storage.class_by_code(code)
        if not cls:
            await message.answer(t("join.bad_code", lang))
            return
        await state.set_state(JoinClassState.waiting_nickname)
        await state.update_data(class_id=cls["id"], class_name=cls["name"])
        await message.answer(t("join.ask_nickname", lang))

    dp.message.register(_join_cmd, Command("join"))

    async def _join_nickname_text(message: Message, state: FSMContext) -> None:
        if not message.from_user or not message.text:
            return
        nickname = message.text.strip()[:40]
        data = await state.get_data()
        class_id = int(data.get("class_id", 0))
        class_name = str(data.get("class_name", ""))
        s = await storage.get_user_settings(message.from_user.id)
        lang = s.get("language", "ru")
        if not class_id:
            await state.clear()
            await message.answer(t("join.bad_code", lang))
            return
        ok = await storage.join_class(class_id, message.from_user.id, nickname)
        await state.clear()
        if ok:
            await message.answer(t("join.ok", lang, class_name=class_name, nickname=nickname))
        else:
            await message.answer(t("join.already", lang))

    dp.message.register(_join_nickname_text, JoinClassState.waiting_nickname, F.text)

    # ---- family share: /share_progress, /share_certificate ---------------

    async def _share_progress_cmd(message: Message) -> None:
        if not message.from_user or message.bot is None:
            return
        u = message.from_user
        full_name = f"{u.first_name or ''} {u.last_name or ''}".strip()
        xp_state = await storage.get_xp(u.id)
        me = await message.bot.get_me()
        username = me.username or "spasai_bot"
        text = share_progress_text(full_name=full_name or None, xp_state=xp_state, bot_username=username)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📨 Отправить родителям", url=telegram_share_url(text))]
            ]
        )
        await message.answer("📣 <b>Поделиться прогрессом</b>\n\n<code>" + text + "</code>", reply_markup=kb)
        grant = await _grant_xp(u.id, "shared")
        await _maybe_celebrate(message, grant)

    dp.message.register(_share_progress_cmd, Command("share_progress"))

    async def _share_certificate_cmd(message: Message) -> None:
        if not message.from_user or message.bot is None:
            return
        cur = await storage.db.execute(
            "SELECT code, full_name FROM certificates WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (message.from_user.id,),
        )
        row = await cur.fetchone()
        if not row:
            await _say(
                message,
                "Сертификата ещё нет. Заверши минимум "
                f"{CERTIFICATE_THRESHOLD} сценариев и забери: /certificate",
            )
            return
        code, full_name = row[0], row[1]
        me = await message.bot.get_me()
        username = me.username or "spasai_bot"
        text = share_certificate_text(full_name=full_name, code=code, bot_username=username)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📨 Отправить родителям", url=telegram_share_url(text))]
            ]
        )
        await message.answer(
            "🎓 <b>Поделиться сертификатом</b>\n\n<code>" + text + "</code>", reply_markup=kb
        )
        grant = await _grant_xp(message.from_user.id, "shared")
        await _maybe_celebrate(message, grant)

    dp.message.register(_share_certificate_cmd, Command("share_certificate"))

    # ---- МЧС RSS subscriptions (C7) -------------------------------------

    async def _subscribe_alerts_cmd(message: Message, command: CommandObject) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        region = (command.args or "").strip().lower()
        if not region:
            avail = ", ".join(known_regions())
            await message.answer(t("alerts.usage", lang) + f"\n\n<i>{avail}</i>")
            return
        await storage.add_alert_subscription(message.from_user.id, region)
        await message.answer(t("alerts.subscribed", lang, region=region))

    dp.message.register(_subscribe_alerts_cmd, Command("subscribe_alerts"))

    async def _unsubscribe_alerts_cmd(message: Message) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        await storage.remove_alert_subscription(message.from_user.id)
        await message.answer(t("alerts.unsubscribed", lang))

    dp.message.register(_unsubscribe_alerts_cmd, Command("unsubscribe_alerts"))

    async def _my_alerts_cmd(message: Message) -> None:
        if not message.from_user:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        regs = await storage.list_alert_subscriptions(message.from_user.id)
        if not regs:
            await message.answer(t("alerts.list_empty", lang))
            return
        body = t("alerts.list_title", lang) + "\n" + "\n".join(f"• {r}" for r in regs)
        await message.answer(body)

    dp.message.register(_my_alerts_cmd, Command("my_alerts"))

    # ---- GigaChat Vision: photo triage (C2) -----------------------------

    async def _photo_handler(message: Message) -> None:
        if not message.photo or not message.from_user or message.bot is None:
            return
        s = await storage.get_user_settings(message.from_user.id)
        lang = normalize_lang(s.get("language", "ru"))
        if not vision_enabled():
            await _say(message, t("vision.disabled", lang))
            return

        # Pick the largest variant.
        photo = message.photo[-1]
        try:
            file = await message.bot.get_file(photo.file_id)
            buf = await message.bot.download_file(file.file_path)
            image_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
        except Exception as exc:
            log.warning("photo download failed: %s", exc)
            await _say(message, t("vision.error", lang))
            return

        await message.answer(t("vision.processing", lang))
        result = await triage_photo(image_bytes, user_id=message.from_user.id)
        if result == "rate_limit":
            await _say(message, t("vision.too_many", lang))
            return
        if result is None:
            await _say(message, t("vision.error", lang))
            return

        await storage.log_event(
            message.from_user.id,
            "vision_triage",
            f"{result.category}/{result.severity}/{result.scenario_id}",
        )
        rows: list[list[InlineKeyboardButton]] = []
        if result.scenario_id and result.scenario_id != "unknown":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📖 Открыть сценарий",
                        callback_data=f"scn:{result.scenario_id}",
                    )
                ]
            )
        rows.append([InlineKeyboardButton(text="🆘 SOS", callback_data="menu:sos")])
        body = (
            f"<b>Триаж по фото.</b>\n\n"
            f"Категория: <b>{result.category}</b>\n"
            f"Степень: <b>{result.severity}</b>\n\n"
            f"{result.advice}\n\n"
            f"{t('vision.disclaimer', lang)}"
        )
        await message.answer(body, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    dp.message.register(_photo_handler, F.photo)

    # ---- /admin_export (H4) + /audit (H1 admin) -------------------------

    async def _admin_export_cmd(message: Message, command: CommandObject) -> None:
        if not message.from_user:
            return
        admin_id = os.getenv("ADMIN_ID")
        if not admin_id or str(message.from_user.id) != str(admin_id):
            return  # silently ignore non-admins
        table = (command.args or "events").strip().lower()
        try:
            cols, rows = await storage.export_table(table)
        except ValueError:
            await message.answer(
                "Неизвестная таблица. Доступно: users, events, feedback, "
                "test_results, aed_submissions, certificates, user_settings, "
                "user_xp, classes, class_members, sos_contacts, ab_assignments, "
                "consent_log, audit_log, alert_subscriptions."
            )
            return
        import csv as _csv
        import io as _io

        buf = _io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(cols)
        for r in rows:
            writer.writerow(r)
        payload = buf.getvalue().encode("utf-8")
        await storage.audit(
            "admin_export",
            actor_id=message.from_user.id,
            target=table,
            details=f"rows={len(rows)}",
        )
        await message.answer_document(
            BufferedInputFile(payload, filename=f"{table}.csv"),
            caption=f"📦 {table}: {len(rows)} строк",
        )

    dp.message.register(_admin_export_cmd, Command("admin_export"))

    async def _audit_cmd(message: Message) -> None:
        if not message.from_user:
            return
        admin_id = os.getenv("ADMIN_ID")
        if not admin_id or str(message.from_user.id) != str(admin_id):
            return
        rows = await storage.list_audit(limit=50)
        if not rows:
            await message.answer("Журнал аудита пуст.")
            return
        lines = [f"📋 Audit log (последние {len(rows)}):", ""]
        for r in rows:
            lines.append(
                f"<code>{r['ts']}</code> {r['action']} "
                f"actor={r['actor_id']} target={r['target']} {r['details'] or ''}"
            )
        await message.answer("\n".join(lines)[:4000])

    dp.message.register(_audit_cmd, Command("audit"))

    # ---- voice STT (Yandex SpeechKit, optional) --------------------------

    async def _voice_handler(message: Message, state: FSMContext) -> None:
        if not message.voice or not message.from_user or message.bot is None:
            return
        if not stt_enabled():
            await _say(
                message,
                "🎤 Распознавание голоса пока выключено. Напиши вопрос текстом.",
            )
            return
        try:
            file = await message.bot.get_file(message.voice.file_id)
            buffer = await message.bot.download_file(file.file_path)
            audio = buffer.read() if hasattr(buffer, "read") else bytes(buffer)
        except Exception as exc:
            log.warning("voice download failed: %s", exc)
            await _say(message, "Не получилось скачать голосовое. Попробуй текстом.")
            return
        text = await transcribe_ogg(audio)
        if not text:
            await _say(
                message,
                "Не разобрал голосовое. Попробуй ещё раз или напиши текстом.",
            )
            return
        await storage.log_event(message.from_user.id, "voice_stt", text[:200])
        await message.answer(f"🎤 Я услышал: <i>{text}</i>")
        answer = await ask_llm(text)
        if answer:
            await message.answer(answer, reply_markup=main_menu_kb())
        else:
            await message.answer(
                "Свободные вопросы пока не подключены. Попробуй сценарий из меню.",
                reply_markup=main_menu_kb(),
            )
        _ = state

    dp.message.register(_voice_handler, F.voice)

    # ---- end of new commands; fallback below -----------------------------

    async def _fallback_text(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        await storage.log_event(message.from_user.id, "free_text", (message.text or "")[:200])
        await message.answer("Думаю…")
        answer = await ask_llm(message.text or "")
        if not answer:
            answer = (
                "Свободные вопросы пока не подключены (нужен ключ GigaChat / YandexGPT).\n"
                "Попробуй выбрать сценарий из меню — там пошаговый алгоритм."
            )
        await message.answer(answer, reply_markup=main_menu_kb())
        _ = state

    dp.message.register(_fallback_text, F.text)
