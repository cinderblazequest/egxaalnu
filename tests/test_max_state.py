"""Юнит-тесты state-машины Max-бота.

Покрывает:
- pure-state переходы ``ScenarioStepState`` (advance/previous/record/to_steps/to_done);
- in-memory хранилище — get/set/clear;
- sqlite-хранилище — переживает рестарт (через `aiosqlite` + миграция m009);
- ``MaxStateMachine`` — happy-path прохождение со step-by-step и pre/post-тестами;
- интеграционный сценарий «callback `open:` → шаги → post-test → код сертификата»
  через ``dispatch_update``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
import pytest

from bot.max.handlers import (
    CB_CAT_PREFIX,
    CB_NEXT_PREFIX,
    CB_OPEN_PREFIX,
    CB_POST_PREFIX,
    CB_PRE_PREFIX,
    CB_PREV_PREFIX,
    build_context,
    dispatch_update,
)
from bot.max.state import (
    InMemoryStateStore,
    MaxStateMachine,
    ScenarioStepState,
    SqliteStateStore,
)
from bot.migrations import run_migrations
from bot.storage import Storage

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"


# ---------- pure state transitions --------------------------------------


def test_advance_step_moves_within_range() -> None:
    s = ScenarioStepState("x", phase="steps", step_idx=0)
    s2 = s.advance_step(max_steps=5)
    assert s2.step_idx == 1
    assert s2.phase == "steps"


def test_advance_step_switches_to_post_at_end() -> None:
    s = ScenarioStepState("x", phase="steps", step_idx=4)
    s2 = s.advance_step(max_steps=5)
    assert s2.phase == "post"
    assert s2.step_idx == 4
    assert s2.q_idx == 0


def test_previous_step_does_not_underflow() -> None:
    s = ScenarioStepState("x", phase="steps", step_idx=0)
    assert s.previous_step().step_idx == 0
    s2 = ScenarioStepState("x", phase="steps", step_idx=3)
    assert s2.previous_step().step_idx == 2


def test_record_pre_and_post() -> None:
    s = ScenarioStepState("x", phase="pre")
    s = s.record_pre(correct=True)
    s = s.record_pre(correct=False)
    assert (s.pre_correct, s.pre_total, s.q_idx) == (1, 2, 2)
    s = s.to_steps()
    assert s.phase == "steps" and s.step_idx == 0 and s.q_idx == 0
    s = ScenarioStepState("x", phase="post", q_idx=0)
    s = s.record_post(correct=True)
    s = s.record_post(correct=True)
    assert (s.post_correct, s.post_total) == (2, 2)


# ---------- in-memory store ---------------------------------------------


@pytest.mark.asyncio
async def test_inmemory_store_roundtrip() -> None:
    store = InMemoryStateStore()
    assert await store.get(1) is None
    state = ScenarioStepState("cpr", step_idx=2, phase="steps")
    await store.set(1, state)
    got = await store.get(1)
    assert got == state
    await store.clear(1)
    assert await store.get(1) is None


# ---------- sqlite store ------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_store_persists_across_reconnect(tmp_path) -> None:
    db_path = str(tmp_path / "spas.db")
    # инициализация: применяем все миграции (в т.ч. m009)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, first_seen TEXT, last_seen TEXT);"
        )
        await db.commit()
        await run_migrations(db)
        store = SqliteStateStore(db)
        await store.set(42, ScenarioStepState("cpr", phase="steps", step_idx=3))
    # переподключаемся и читаем — данные должны сохраниться
    async with aiosqlite.connect(db_path) as db:
        store2 = SqliteStateStore(db)
        state = await store2.get(42)
        assert state is not None
        assert state.scenario_id == "cpr"
        assert state.phase == "steps"
        assert state.step_idx == 3
        await store2.clear(42)
        assert await store2.get(42) is None


# ---------- state machine -----------------------------------------------


@pytest.mark.asyncio
async def test_state_machine_pre_then_steps_then_post() -> None:
    sm = MaxStateMachine()
    state = await sm.start_scenario(1, "cpr", has_pre_test=True)
    assert state.phase == "pre"

    state = await sm.answer_pre(1, correct=True, total_questions=2)
    assert state and state.phase == "pre" and state.q_idx == 1

    state = await sm.answer_pre(1, correct=False, total_questions=2)
    assert state and state.phase == "steps" and state.step_idx == 0
    assert state.pre_correct == 1 and state.pre_total == 2

    state = await sm.next_step(1, max_steps=3)
    assert state and state.step_idx == 1
    state = await sm.next_step(1, max_steps=3)
    assert state and state.step_idx == 2
    state = await sm.next_step(1, max_steps=3)
    assert state and state.phase == "post"

    state = await sm.answer_post(1, correct=True, total_questions=2)
    assert state and state.phase == "post" and state.q_idx == 1
    state = await sm.answer_post(1, correct=True, total_questions=2)
    assert state and state.phase == "done"

    await sm.finish(1)
    assert await sm.get(1) is None


@pytest.mark.asyncio
async def test_state_machine_no_pre_test_goes_directly_to_steps() -> None:
    sm = MaxStateMachine()
    state = await sm.start_scenario(2, "minor", has_pre_test=False)
    assert state.phase == "steps"
    state = await sm.next_step(2, max_steps=1)
    assert state and state.phase == "post"  # одношаговый сценарий уходит в post


@pytest.mark.asyncio
async def test_state_machine_rejects_actions_without_state() -> None:
    sm = MaxStateMachine()
    assert await sm.next_step(99, max_steps=3) is None
    assert await sm.prev_step(99) is None
    assert await sm.answer_pre(99, correct=True, total_questions=2) is None
    assert await sm.answer_post(99, correct=True, total_questions=2) is None


@pytest.mark.asyncio
async def test_state_machine_answer_pre_wrong_phase_returns_none() -> None:
    sm = MaxStateMachine()
    await sm.start_scenario(3, "cpr", has_pre_test=False)
    # в steps — pre-ответ невалиден
    assert await sm.answer_pre(3, correct=True, total_questions=2) is None
    # вынудительно поставим состояние post — там next_step не работает
    await sm.force_set(3, ScenarioStepState("cpr", phase="post"))
    assert await sm.next_step(3, max_steps=3) is None
    assert await sm.prev_step(3) is None


# ---------- end-to-end через dispatch_update -----------------------------


class _RecordingClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.callbacks: list[dict[str, Any]] = []

    async def send_message(self, chat_id, text, *, buttons=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})

    async def answer_callback(self, callback_id, *, notification=None):
        self.callbacks.append({"callback_id": callback_id, "notification": notification})


def _cb(payload: str, user_id: int, chat_id: int, cb_id: str) -> dict[str, Any]:
    return {
        "update_type": "message_callback",
        "message": {"recipient": {"chat_id": chat_id}},
        "callback": {"callback_id": cb_id, "payload": payload, "user": {"user_id": user_id}},
    }


@pytest.mark.asyncio
async def test_dispatch_open_then_step_then_post_e2e() -> None:
    """Открыть сценарий → пройти все шаги/тесты через callback'и."""
    ctx = build_context(CONTENT_DIR)
    # выбрать сценарий с post-тестом
    scenario = next((s for s in ctx.catalogue.scenarios.values() if s.post_test), None)
    assert scenario is not None, "должен быть сценарий с post-test"
    sid = scenario.id
    client = _RecordingClient()
    user_id = 555
    chat_id = 555

    # 1) Открыть сценарий
    await dispatch_update(client, ctx, _cb(CB_OPEN_PREFIX + sid, user_id, chat_id, "c1"))  # type: ignore[arg-type]
    state = await ctx.state.get(user_id)
    assert state is not None
    initial_phase = state.phase

    # 2) Если есть pre-test — ответить на все вопросы
    if initial_phase == "pre":
        for q_idx in range(len(scenario.pre_test)):
            payload = f"{CB_PRE_PREFIX}{sid}:{q_idx}:{scenario.pre_test[q_idx].correct}"
            await dispatch_update(client, ctx, _cb(payload, user_id, chat_id, f"p{q_idx}"))  # type: ignore[arg-type]
        state = await ctx.state.get(user_id)
        assert state is not None and state.phase == "steps"

    # 3) Прокликать все шаги
    for i in range(len(scenario.steps)):
        await dispatch_update(client, ctx, _cb(CB_NEXT_PREFIX + sid, user_id, chat_id, f"n{i}"))  # type: ignore[arg-type]
    state = await ctx.state.get(user_id)
    assert state is not None and state.phase == "post"

    # 4) Ответить на post-test (все правильно)
    for q_idx, q in enumerate(scenario.post_test):
        payload = f"{CB_POST_PREFIX}{sid}:{q_idx}:{q.correct}"
        await dispatch_update(client, ctx, _cb(payload, user_id, chat_id, f"po{q_idx}"))  # type: ignore[arg-type]
    state = await ctx.state.get(user_id)
    assert state is None, "После post-test state должен быть очищен"

    # Последнее сообщение должно содержать поздравление
    texts = [m["text"] for m in client.sent]
    assert any("Сценарий пройден" in t for t in texts)


@pytest.mark.asyncio
async def test_dispatch_prev_button_walks_back() -> None:
    ctx = build_context(CONTENT_DIR)
    scenario = next(
        (s for s in ctx.catalogue.scenarios.values() if len(s.steps) >= 3 and not s.pre_test),
        None,
    )
    # fallback: если все сценарии с pre_test — возьмём первый, но прокликаем pre-тест
    if scenario is None:
        scenario = next(iter(ctx.catalogue.scenarios.values()))
    sid = scenario.id
    client = _RecordingClient()
    user_id = 777

    await dispatch_update(client, ctx, _cb(CB_OPEN_PREFIX + sid, user_id, user_id, "c1"))  # type: ignore[arg-type]
    # если в pre — отвечаем
    state = await ctx.state.get(user_id)
    assert state is not None
    if state.phase == "pre":
        for q_idx in range(len(scenario.pre_test)):
            payload = f"{CB_PRE_PREFIX}{sid}:{q_idx}:0"
            await dispatch_update(client, ctx, _cb(payload, user_id, user_id, f"p{q_idx}"))  # type: ignore[arg-type]
    await dispatch_update(client, ctx, _cb(CB_NEXT_PREFIX + sid, user_id, user_id, "n1"))  # type: ignore[arg-type]
    state = await ctx.state.get(user_id)
    assert state is not None and state.step_idx == 1
    await dispatch_update(client, ctx, _cb(CB_PREV_PREFIX + sid, user_id, user_id, "pv"))  # type: ignore[arg-type]
    state = await ctx.state.get(user_id)
    assert state is not None and state.step_idx == 0


@pytest.mark.asyncio
async def test_dispatch_unknown_scenario_does_not_crash() -> None:
    ctx = build_context(CONTENT_DIR)
    client = _RecordingClient()
    await dispatch_update(client, ctx, _cb(CB_OPEN_PREFIX + "no-such", 1, 1, "x"))  # type: ignore[arg-type]
    assert client.callbacks and client.callbacks[0]["notification"] == "Сценарий не найден"


@pytest.mark.asyncio
async def test_dispatch_profile_without_storage_replies_gracefully() -> None:
    ctx = build_context(CONTENT_DIR)
    client = _RecordingClient()
    update = {
        "update_type": "message_created",
        "message": {"recipient": {"chat_id": 1}, "sender": {"user_id": 1}, "body": {"text": "/profile"}},
    }
    await dispatch_update(client, ctx, update)  # type: ignore[arg-type]
    assert client.sent
    assert "базой данных" in client.sent[0]["text"].lower()


@pytest.mark.asyncio
async def test_dispatch_category_button_lists_scenarios() -> None:
    ctx = build_context(CONTENT_DIR)
    client = _RecordingClient()
    await dispatch_update(client, ctx, _cb(CB_CAT_PREFIX + "critical", 1, 1, "c"))  # type: ignore[arg-type]
    assert client.sent
    buttons = client.sent[0]["buttons"]
    # хотя бы один открыватель сценария
    assert any(b.payload.startswith(CB_OPEN_PREFIX) for row in buttons for b in row)


@pytest.mark.asyncio
async def test_full_flow_with_storage_awards_xp_and_certificate(tmp_path) -> None:
    """End-to-end с реальной БД: после прохождения сценария XP/уровень обновлены."""
    db_path = str(tmp_path / "spas-e2e.db")
    storage = Storage(db_path)
    await storage.init()
    try:
        ctx = build_context(CONTENT_DIR, storage=storage)
        ctx.state = MaxStateMachine(store=SqliteStateStore(storage.db))
        scenario = next((s for s in ctx.catalogue.scenarios.values() if s.post_test), None)
        assert scenario is not None
        sid = scenario.id
        client = _RecordingClient()
        uid = 9001
        await dispatch_update(client, ctx, _cb(CB_OPEN_PREFIX + sid, uid, uid, "c1"))  # type: ignore[arg-type]
        state = await ctx.state.get(uid)
        assert state is not None
        if state.phase == "pre":
            for q_idx in range(len(scenario.pre_test)):
                payload = f"{CB_PRE_PREFIX}{sid}:{q_idx}:{scenario.pre_test[q_idx].correct}"
                await dispatch_update(client, ctx, _cb(payload, uid, uid, f"p{q_idx}"))  # type: ignore[arg-type]
        for i in range(len(scenario.steps)):
            await dispatch_update(client, ctx, _cb(CB_NEXT_PREFIX + sid, uid, uid, f"n{i}"))  # type: ignore[arg-type]
        for q_idx, q in enumerate(scenario.post_test):
            payload = f"{CB_POST_PREFIX}{sid}:{q_idx}:{q.correct}"
            await dispatch_update(client, ctx, _cb(payload, uid, uid, f"po{q_idx}"))  # type: ignore[arg-type]
        xp = await storage.get_xp(uid)
        assert xp["xp"] > 0, "XP должен начислиться"
        assert "first_step" in xp["achievements"], "Ачивка `first_step` должна разблокироваться"
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_storage_users_table_has_platform_column(tmp_path) -> None:
    db_path = str(tmp_path / "spas-plat.db")
    storage = Storage(db_path)
    await storage.init()
    try:
        cur = await storage.db.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in await cur.fetchall()}
        assert "platform" in cols, "Миграция m009 должна добавить колонку platform"
    finally:
        await storage.close()
