"""Юнит-тесты для bot.max — клиент API и роутинг апдейтов.

Сетевые вызовы Max API изолируются через `aresponses` (или fallback на
``aiohttp.test_utils``-mock). Тут используем простой стаб: мокируем
``aiohttp.ClientSession.request`` через monkeypatching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bot.max.client import MaxAPIError, MaxBotClient, MaxButton, keyboard
from bot.max.handlers import (
    CB_CAT_PREFIX,
    CB_OPEN_PREFIX,
    HELP_TEXT,
    build_context,
    dispatch_update,
    extract_chat_id,
    main_menu_buttons,
    render_aed_list,
    render_dispatcher_intro,
    render_panic_intro,
    render_scenario,
)

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"


# --- Клиент API ----------------------------------------------------------


class _StubResponse:
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> _StubResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def json(self) -> Any:
        return self._body


class _StubSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[_StubResponse] = []

    def queue(self, status: int, body: Any) -> None:
        self.responses.append(_StubResponse(status, body))

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> _StubResponse:
        self.calls.append({"method": method, "url": url, "params": params, "json": json})
        if not self.responses:
            return _StubResponse(200, {})
        return self.responses.pop(0)

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_keyboard_payload_shape() -> None:
    kb = keyboard([[MaxButton("A", "p1"), MaxButton("Open", url="https://x")]])
    assert kb["type"] == "inline_keyboard"
    btns = kb["payload"]["buttons"]
    assert btns[0][0] == {"type": "callback", "text": "A", "payload": "p1"}
    assert btns[0][1] == {"type": "link", "text": "Open", "url": "https://x"}


@pytest.mark.asyncio
async def test_send_message_uses_post_with_chat_id() -> None:
    session = _StubSession()
    session.queue(200, {"message": {"mid": "abc"}})
    async with MaxBotClient("TOKEN", session=session) as client:  # type: ignore[arg-type]
        await client.send_message(42, "hi", buttons=[[MaxButton("X", "y")]])
    call = session.calls[-1]
    assert call["method"] == "POST"
    assert call["url"].endswith("/messages")
    assert call["params"]["chat_id"] == 42
    assert call["params"]["access_token"] == "TOKEN"
    assert call["json"]["text"] == "hi"
    attachments = call["json"]["attachments"]
    assert attachments[0]["type"] == "inline_keyboard"


@pytest.mark.asyncio
async def test_get_updates_passes_marker_and_types() -> None:
    session = _StubSession()
    session.queue(200, {"updates": [], "marker": 7})
    async with MaxBotClient("T", session=session) as client:  # type: ignore[arg-type]
        out = await client.get_updates(marker=4, types=["message_created"], timeout=10)
    call = session.calls[-1]
    assert call["method"] == "GET"
    assert call["url"].endswith("/updates")
    assert call["params"]["marker"] == 4
    assert call["params"]["types"] == "message_created"
    assert out["marker"] == 7


@pytest.mark.asyncio
async def test_api_error_raised_on_400() -> None:
    session = _StubSession()
    session.queue(401, {"code": "verify.token", "message": "bad"})
    async with MaxBotClient("T", session=session) as client:  # type: ignore[arg-type]
        with pytest.raises(MaxAPIError) as ei:
            await client.get_me()
    assert ei.value.status == 401


def test_token_required() -> None:
    with pytest.raises(ValueError):
        MaxBotClient("")


# --- Хендлеры / контент --------------------------------------------------


def test_build_context_loads_real_content() -> None:
    ctx = build_context(CONTENT_DIR)
    assert ctx.catalogue.scenarios, "должны загрузиться сценарии"
    assert ctx.dispatcher.questions, "должны быть вопросы 112"
    assert ctx.panic.breathing_total_cycles >= 1


def test_render_scenario_includes_title_and_steps() -> None:
    ctx = build_context(CONTENT_DIR)
    sid, scenario = next(iter(ctx.catalogue.scenarios.items()))
    text = render_scenario(scenario)
    assert scenario.title in text
    assert scenario.steps[0] in text
    assert "112" in text or scenario.phone in text


def test_render_panic_intro() -> None:
    ctx = build_context(CONTENT_DIR)
    text = render_panic_intro(ctx.panic)
    assert "Паника" in text
    assert "Дыхание" in text


def test_render_dispatcher_intro() -> None:
    ctx = build_context(CONTENT_DIR)
    text = render_dispatcher_intro(ctx.dispatcher)
    assert "112" in text


def test_render_aed_list() -> None:
    ctx = build_context(CONTENT_DIR)
    text = render_aed_list(ctx.catalogue, limit=3)
    assert "АНД" in text
    assert "Всего в базе" in text


def test_main_menu_has_three_categories() -> None:
    rows = main_menu_buttons()
    payloads = [b.payload for row in rows for b in row]
    assert any(p.startswith(CB_CAT_PREFIX) for p in payloads)
    assert any(p == "cmd:panic" for p in payloads)
    assert any(p == "cmd:dispatcher" for p in payloads)


# --- dispatch_update -----------------------------------------------------


class _RecordingClient:
    """Минимальный duck-type клиент, не делающий сети, чтобы тестировать роутинг."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.callbacks: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str, *, buttons=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {}

    async def answer_callback(self, callback_id: str, *, notification: str | None = None):
        self.callbacks.append({"callback_id": callback_id, "notification": notification})
        return {}


@pytest.mark.asyncio
async def test_dispatch_handles_message_created_for_help() -> None:
    ctx = build_context(CONTENT_DIR)
    client = _RecordingClient()
    update = {
        "update_type": "message_created",
        "message": {
            "recipient": {"chat_id": 100},
            "body": {"text": "/help"},
        },
    }
    await dispatch_update(client, ctx, update)  # type: ignore[arg-type]
    # /help отправляет два сообщения: приветствие и HELP_TEXT.
    assert len(client.sent) == 2
    assert client.sent[1]["text"] == HELP_TEXT


@pytest.mark.asyncio
async def test_dispatch_handles_callback_for_open_scenario() -> None:
    ctx = build_context(CONTENT_DIR)
    sid = next(iter(ctx.catalogue.scenarios))
    client = _RecordingClient()
    update = {
        "update_type": "message_callback",
        "message": {"recipient": {"chat_id": 7}},
        "callback": {"callback_id": "cb1", "payload": CB_OPEN_PREFIX + sid},
    }
    await dispatch_update(client, ctx, update)  # type: ignore[arg-type]
    assert client.sent and ctx.catalogue.scenarios[sid].title in client.sent[0]["text"]
    assert client.callbacks and client.callbacks[0]["callback_id"] == "cb1"


@pytest.mark.asyncio
async def test_dispatch_handles_callback_for_category() -> None:
    ctx = build_context(CONTENT_DIR)
    client = _RecordingClient()
    update = {
        "update_type": "message_callback",
        "message": {"recipient": {"chat_id": 7}},
        "callback": {"callback_id": "cb2", "payload": CB_CAT_PREFIX + "critical"},
    }
    await dispatch_update(client, ctx, update)  # type: ignore[arg-type]
    assert client.sent
    text = client.sent[0]["text"]
    assert "critical" in text


@pytest.mark.asyncio
async def test_dispatch_replies_on_bot_started() -> None:
    ctx = build_context(CONTENT_DIR)
    client = _RecordingClient()
    update = {
        "update_type": "bot_started",
        "chat_id": 55,
    }
    await dispatch_update(client, ctx, update)  # type: ignore[arg-type]
    assert client.sent and "СПАС" in client.sent[0]["text"]


def test_extract_chat_id_from_callback() -> None:
    update = {
        "update_type": "message_callback",
        "message": {"recipient": {"chat_id": 999}},
        "callback": {"user": {"user_id": 12}},
    }
    assert extract_chat_id(update) == 999


def test_extract_chat_id_falls_back_to_user_id() -> None:
    update = {
        "update_type": "message_created",
        "message": {"sender": {"user_id": 321}, "body": {"text": "/sos"}},
    }
    assert extract_chat_id(update) == 321


# --- Sanity: keyboard JSON-сериализуемый ---------------------------------


def test_keyboard_json_serialisable() -> None:
    kb = keyboard([[MaxButton("Жми", "p1")]])
    json.dumps(kb)  # должно не падать
