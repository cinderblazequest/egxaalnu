"""Геймификация: XP, уровни, достижения, серии (streak).

Не самостоятельная история — слой вокруг ``Storage``. Для каждого
пользователя ведётся:
  - суммарный XP
  - уровень (вычисляется из XP по таблице ``LEVEL_THRESHOLDS``)
  - список разблокированных ачивок
  - текущая серия дней подряд
  - дата последней активности

Идея: сделать обучение возвращающимся, не превращая бота в TikTok.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

# XP grants per event (kept conservative so users don't grind).
XP_FOR_SCENARIO = 30
XP_FOR_PERFECT_POST_TEST = 20
XP_FOR_DISPATCHER_RUN = 10
XP_FOR_PANIC_USE = 5
XP_FOR_DAILY_RETURN = 15

# (level, total xp required, label).
LEVEL_THRESHOLDS: list[tuple[int, int, str]] = [
    (1, 0, "Новичок"),
    (2, 30, "Слушатель"),
    (3, 90, "Помощник"),
    (4, 200, "Спасатель"),
    (5, 400, "Опытный спасатель"),
    (6, 700, "Мастер"),
    (7, 1100, "Герой"),
    (8, 1700, "Легенда"),
]


@dataclass(frozen=True)
class Achievement:
    code: str
    title: str
    description: str
    xp: int


ACHIEVEMENTS: dict[str, Achievement] = {
    "first_step": Achievement("first_step", "Первый шаг", "Прошёл первый сценарий до конца", 10),
    "five_in_one": Achievement("five_in_one", "Пять в копилку", "Пять разных сценариев до конца", 25),
    "ten_in_one": Achievement("ten_in_one", "Десятка", "Десять разных сценариев до конца", 50),
    "all_critical": Achievement(
        "all_critical", "Спасатель критики", "Все критические сценарии (СЛР, удушье, ...)", 60
    ),
    "perfect_post": Achievement("perfect_post", "Идеально", "Полный балл на post-test любого сценария", 15),
    "panic_calmed": Achievement("panic_calmed", "Спокойствие", "Прошёл panic-режим до конца", 5),
    "dispatcher_pro": Achievement("dispatcher_pro", "Готов к 112", "Прошёл чек-лист диспетчера", 10),
    "streak_3": Achievement("streak_3", "Серия 3", "Три дня подряд", 15),
    "streak_7": Achievement("streak_7", "Серия 7", "Семь дней подряд", 35),
    "shared": Achievement("shared", "Поделился", "Поделился сертификатом или прогрессом", 10),
}


def level_for_xp(xp: int) -> tuple[int, str]:
    chosen = LEVEL_THRESHOLDS[0]
    for entry in LEVEL_THRESHOLDS:
        if xp >= entry[1]:
            chosen = entry
        else:
            break
    return chosen[0], chosen[2]


def next_level_target(xp: int) -> tuple[int, int] | None:
    for entry in LEVEL_THRESHOLDS:
        if entry[1] > xp:
            return entry[0], entry[1]
    return None


def _today_str() -> str:
    return _dt.date.today().isoformat()


def update_streak(prev_last_active: str | None, today: str | None = None) -> int:
    """Return new streak length given the last_active date string and today.

    +1 if last active was yesterday, reset to 1 otherwise. None last → 1.
    """
    today_d = _dt.date.fromisoformat(today) if today else _dt.date.today()
    if not prev_last_active:
        return 1
    try:
        # last_active stored as full ISO datetime; pull the date prefix.
        last_d = _dt.date.fromisoformat(prev_last_active[:10])
    except ValueError:
        return 1
    diff = (today_d - last_d).days
    if diff <= 0:
        # already counted today
        return 0
    if diff == 1:
        return 1  # +1 streak (caller adds)
    return -1  # reset to 1


@dataclass
class XPDelta:
    xp_gained: int
    new_level: int
    new_label: str
    leveled_up: bool
    new_achievements: list[Achievement]
    streak_days: int


def evaluate_event(
    *,
    state: dict,
    event: str,
    payload: str | None = None,
    completed_scenarios: set[str] | None = None,
    perfect_post: bool = False,
    today: str | None = None,
) -> XPDelta:
    """Pure function: given current XP state and an event, returns the delta.

    Caller persists the result to storage.
    ``state`` shape: ``{"xp": int, "level": int, "achievements": list[str], "streak_days": int, "last_active": str|None}``.
    """
    xp = int(state.get("xp", 0))
    achievements = list(state.get("achievements", []))
    streak = int(state.get("streak_days", 0))
    last_active = state.get("last_active")

    gained = 0

    if event == "scenario_complete":
        gained += XP_FOR_SCENARIO
        if perfect_post:
            gained += XP_FOR_PERFECT_POST_TEST
    elif event == "dispatcher_done":
        gained += XP_FOR_DISPATCHER_RUN
    elif event == "panic_breathe":
        gained += XP_FOR_PANIC_USE
    elif event == "shared":
        # additive bonus for share_progress / share_certificate
        gained += 5

    today_str = today or _today_str()
    if last_active and last_active[:10] == today_str:
        streak_increment = 0
    else:
        streak_increment = update_streak(last_active, today=today_str)
        if streak_increment == 1:
            streak += 1
            gained += XP_FOR_DAILY_RETURN
        elif streak_increment == -1:
            streak = 1
            gained += XP_FOR_DAILY_RETURN
        else:
            streak = max(streak, 1)
            gained += XP_FOR_DAILY_RETURN

    new_unlocked: list[Achievement] = []

    def unlock(code: str) -> None:
        if code not in achievements and code in ACHIEVEMENTS:
            achievements.append(code)
            ach = ACHIEVEMENTS[code]
            new_unlocked.append(ach)

    completed = completed_scenarios or set()
    if event == "scenario_complete":
        if completed:
            if len(completed) >= 1:
                unlock("first_step")
            if len(completed) >= 5:
                unlock("five_in_one")
            if len(completed) >= 10:
                unlock("ten_in_one")
        if perfect_post:
            unlock("perfect_post")
    elif event == "dispatcher_done":
        unlock("dispatcher_pro")
    elif event == "panic_breathe":
        unlock("panic_calmed")
    elif event == "shared":
        unlock("shared")

    if streak >= 3:
        unlock("streak_3")
    if streak >= 7:
        unlock("streak_7")

    for ach in new_unlocked:
        gained += ach.xp

    new_xp = xp + gained
    prev_level = int(state.get("level", 1))
    new_level, new_label = level_for_xp(new_xp)
    leveled_up = new_level > prev_level

    return XPDelta(
        xp_gained=gained,
        new_level=new_level,
        new_label=new_label,
        leveled_up=leveled_up,
        new_achievements=new_unlocked,
        streak_days=streak,
    )


def render_profile(state: dict) -> str:
    xp = int(state.get("xp", 0))
    level, label = level_for_xp(xp)
    next_target = next_level_target(xp)
    lines = [
        "<b>🎓 Твой профиль СПАС</b>",
        f"Уровень: <b>{level}</b> · {label}",
        f"XP: <b>{xp}</b>",
        f"Серия дней: <b>{state.get('streak_days', 0)}</b>",
    ]
    if next_target is not None:
        _, target_xp = next_target
        lines.append(f"До следующего уровня: <b>{target_xp - xp}</b> XP")
    achievements = state.get("achievements") or []
    if achievements:
        lines.append("\n<b>Ачивки:</b>")
        for code in achievements:
            ach = ACHIEVEMENTS.get(code)
            if ach:
                lines.append(f"• 🏅 {ach.title} — <i>{ach.description}</i>")
    else:
        lines.append("\n<i>Ачивки появятся, как только пройдёшь сценарии.</i>")
    return "\n".join(lines)
