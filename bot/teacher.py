"""Режим учителя: создать класс → раздать invite-код → видеть прогресс.

Workflow:
  /teacher          — создать новый класс (state ``TeacherState.naming``)
  /teacher_dashboard — показать список созданных классов и прогресс
  /join CODE         — ученик присоединяется к классу

Анонимизация: учитель видит только nickname, который ученик задал
сам при подключении. Если ученик не задал — показывается ``user_<id>``.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class TeacherState(StatesGroup):
    naming = State()


class JoinClassState(StatesGroup):
    waiting_nickname = State()


def teacher_classes_kb(classes: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📋 {c['name']} ({c['invite_code']})",
                callback_data=f"teacher_view:{c['id']}",
            )
        ]
        for c in classes
    ]
    rows.append([InlineKeyboardButton(text="➕ Создать класс", callback_data="teacher:new")])
    rows.append([InlineKeyboardButton(text="« в меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_class_progress(class_info: dict, members: list[dict]) -> str:
    if not members:
        return (
            f"📋 <b>{class_info['name']}</b>\n"
            f"Код для учеников: <code>{class_info['invite_code']}</code>\n\n"
            "Пока никто не присоединился. Раздай код ученикам:\n"
            "они откроют бота и пришлют /join <code>" + class_info["invite_code"] + "</code>"
        )
    lines = [
        f"📋 <b>{class_info['name']}</b> · <code>{class_info['invite_code']}</code>",
        f"Учеников: <b>{len(members)}</b>",
        "",
        "<b>Топ по XP:</b>",
    ]
    for i, m in enumerate(members[:15], start=1):
        lines.append(
            f"{i}. <b>{m['nickname']}</b> — Lv {m['level']} · {m['xp']} XP · " f"{m['completed']} сценариев"
        )
    return "\n".join(lines)
