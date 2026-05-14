"""State-машина прохождения сценария Max-пользователем.

В Telegram прохождение управляется через aiogram FSM (см. ``bot.handlers``).
Max API не предоставляет аналога: для нас это сводится к простому
маппингу ``user_id -> ScenarioStepState`` плюс write-through в SQLite,
чтобы прохождение пережило рестарт процесса.

Хранилище разделено на два уровня:

* ``InMemoryStateStore`` — быстрый dict, всё в RAM. Используется по
  умолчанию (для тестов и при отсутствии storage).
* ``SqliteStateStore`` — обёртка вокруг ``aiosqlite.Connection``,
  пишет в таблицу ``max_user_state`` (миграция m009).

``MaxStateMachine`` — фасад, не зависит от способа хранения.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

import aiosqlite

log = logging.getLogger("spas.max.state")


Phase = Literal["pre", "steps", "post", "done"]


@dataclass(frozen=True)
class ScenarioStepState:
    """Снимок прогресса пользователя по конкретному сценарию.

    ``phase`` — какой блок сейчас:
      ``pre``    — отвечает на pre-test;
      ``steps``  — кликает по шагам;
      ``post``   — отвечает на post-test;
      ``done``   — сценарий завершён (state можно очистить).

    ``step_idx`` — индекс шага, ``q_idx`` — индекс вопроса теста.
    Счётчики ``*_correct``/``*_total`` нужны для статистики и для XP.
    """

    scenario_id: str
    phase: Phase = "pre"
    step_idx: int = 0
    q_idx: int = 0
    pre_correct: int = 0
    pre_total: int = 0
    post_correct: int = 0
    post_total: int = 0

    def advance_step(self, max_steps: int) -> ScenarioStepState:
        """Перейти к следующему шагу. На последнем — переключиться в ``post``."""
        nxt = self.step_idx + 1
        if nxt >= max_steps:
            return replace(self, phase="post", step_idx=max_steps - 1, q_idx=0)
        return replace(self, step_idx=nxt)

    def previous_step(self) -> ScenarioStepState:
        """Шаг назад (не уходим в минус)."""
        return replace(self, step_idx=max(0, self.step_idx - 1))

    def record_pre(self, *, correct: bool) -> ScenarioStepState:
        return replace(
            self,
            q_idx=self.q_idx + 1,
            pre_correct=self.pre_correct + (1 if correct else 0),
            pre_total=self.pre_total + 1,
        )

    def record_post(self, *, correct: bool) -> ScenarioStepState:
        return replace(
            self,
            q_idx=self.q_idx + 1,
            post_correct=self.post_correct + (1 if correct else 0),
            post_total=self.post_total + 1,
        )

    def to_steps(self) -> ScenarioStepState:
        """Перейти из pre-теста к самим шагам (после последнего вопроса)."""
        return replace(self, phase="steps", step_idx=0, q_idx=0)

    def to_done(self) -> ScenarioStepState:
        return replace(self, phase="done")


class StateStore(Protocol):
    """Абстрактное хранилище состояний Max-сценариев."""

    async def get(self, user_id: int) -> ScenarioStepState | None: ...
    async def set(self, user_id: int, state: ScenarioStepState) -> None: ...
    async def clear(self, user_id: int) -> None: ...


@dataclass
class InMemoryStateStore:
    """Простое in-process хранилище. Не переживает рестарт."""

    _data: dict[int, ScenarioStepState] = field(default_factory=dict)

    async def get(self, user_id: int) -> ScenarioStepState | None:
        return self._data.get(user_id)

    async def set(self, user_id: int, state: ScenarioStepState) -> None:
        self._data[user_id] = state

    async def clear(self, user_id: int) -> None:
        self._data.pop(user_id, None)


class SqliteStateStore:
    """Хранит состояние в таблице ``max_user_state`` (миграция m009).

    Write-through: при каждой записи коммитит. Кэш в памяти, чтобы
    избежать SELECT на каждый callback.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._cache: dict[int, ScenarioStepState] = {}

    async def get(self, user_id: int) -> ScenarioStepState | None:
        if user_id in self._cache:
            return self._cache[user_id]
        cur = await self._db.execute(
            """
            SELECT scenario_id, phase, step_idx, q_idx,
                   pre_correct, pre_total, post_correct, post_total
            FROM max_user_state WHERE user_id=?
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        state = ScenarioStepState(
            scenario_id=str(row[0]),
            phase=row[1],  # type: ignore[arg-type]
            step_idx=int(row[2]),
            q_idx=int(row[3]),
            pre_correct=int(row[4]),
            pre_total=int(row[5]),
            post_correct=int(row[6]),
            post_total=int(row[7]),
        )
        self._cache[user_id] = state
        return state

    async def set(self, user_id: int, state: ScenarioStepState) -> None:
        now = _dt.datetime.now(_dt.UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO max_user_state(
                user_id, scenario_id, phase, step_idx, q_idx,
                pre_correct, pre_total, post_correct, post_total, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                scenario_id = excluded.scenario_id,
                phase = excluded.phase,
                step_idx = excluded.step_idx,
                q_idx = excluded.q_idx,
                pre_correct = excluded.pre_correct,
                pre_total = excluded.pre_total,
                post_correct = excluded.post_correct,
                post_total = excluded.post_total,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                state.scenario_id,
                state.phase,
                state.step_idx,
                state.q_idx,
                state.pre_correct,
                state.pre_total,
                state.post_correct,
                state.post_total,
                now,
            ),
        )
        await self._db.commit()
        self._cache[user_id] = state

    async def clear(self, user_id: int) -> None:
        await self._db.execute("DELETE FROM max_user_state WHERE user_id=?", (user_id,))
        await self._db.commit()
        self._cache.pop(user_id, None)


class MaxStateMachine:
    """Высокоуровневый фасад поверх ``StateStore``.

    Содержит логику переходов: ``start_scenario``, ``next_step``,
    ``prev_step``, ``answer_pre``, ``answer_post``, ``finish``.
    Хранит инвариант: ``phase`` всегда «правильный» — то есть мы не
    выходим за пределы шагов и тестов.
    """

    def __init__(self, store: StateStore | None = None) -> None:
        self._store: StateStore = store or InMemoryStateStore()

    async def get(self, user_id: int) -> ScenarioStepState | None:
        return await self._store.get(user_id)

    async def start_scenario(
        self,
        user_id: int,
        scenario_id: str,
        *,
        has_pre_test: bool,
    ) -> ScenarioStepState:
        state = ScenarioStepState(
            scenario_id=scenario_id,
            phase="pre" if has_pre_test else "steps",
        )
        await self._store.set(user_id, state)
        return state

    async def answer_pre(
        self,
        user_id: int,
        *,
        correct: bool,
        total_questions: int,
    ) -> ScenarioStepState | None:
        state = await self._store.get(user_id)
        if state is None or state.phase != "pre":
            return None
        state = state.record_pre(correct=correct)
        if state.q_idx >= total_questions:
            state = state.to_steps()
        await self._store.set(user_id, state)
        return state

    async def next_step(self, user_id: int, *, max_steps: int) -> ScenarioStepState | None:
        state = await self._store.get(user_id)
        if state is None or state.phase != "steps":
            return None
        state = state.advance_step(max_steps)
        await self._store.set(user_id, state)
        return state

    async def prev_step(self, user_id: int) -> ScenarioStepState | None:
        state = await self._store.get(user_id)
        if state is None or state.phase != "steps":
            return None
        state = state.previous_step()
        await self._store.set(user_id, state)
        return state

    async def answer_post(
        self,
        user_id: int,
        *,
        correct: bool,
        total_questions: int,
    ) -> ScenarioStepState | None:
        state = await self._store.get(user_id)
        if state is None or state.phase != "post":
            return None
        state = state.record_post(correct=correct)
        if state.q_idx >= total_questions:
            state = state.to_done()
        await self._store.set(user_id, state)
        return state

    async def finish(self, user_id: int) -> None:
        await self._store.clear(user_id)

    async def force_set(self, user_id: int, state: ScenarioStepState) -> None:
        """Прямая запись — на случай восстановления конкретного шага."""
        await self._store.set(user_id, state)
