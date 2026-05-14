"""Tests for the per-user rate-limiter middleware."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from aiogram.types import Message

from bot.middleware.throttle import ThrottleMiddleware


@dataclass
class _FakeUser:
    id: int


def _fake_message(user_id: int = 42) -> Message:
    # bypass aiogram validation by constructing via model_construct
    return Message.model_construct(
        message_id=1, date=int(time.time()), chat=None, from_user=_FakeUser(id=user_id)
    )


def test_throttle_allows_within_limit() -> None:
    mw = ThrottleMiddleware(rate=3, per=1.0)
    msg = _fake_message()

    async def handler(_event, _data):
        return "ok"

    async def run() -> list:
        results = []
        for _ in range(3):
            results.append(await mw(handler, msg, {}))
        return results

    out = asyncio.run(run())
    assert out == ["ok", "ok", "ok"]


def test_throttle_blocks_over_limit() -> None:
    mw = ThrottleMiddleware(rate=2, per=1.0)
    msg = _fake_message()

    async def handler(_event, _data):
        return "ok"

    async def run() -> list:
        results = []
        for _ in range(4):
            results.append(await mw(handler, msg, {}))
        return results

    out = asyncio.run(run())
    # first 2 ok, next 2 are throttled (return None)
    assert out[0] == "ok"
    assert out[1] == "ok"
    assert out[2] is None
    assert out[3] is None


def test_throttle_independent_per_user() -> None:
    mw = ThrottleMiddleware(rate=1, per=10.0)
    msg_a = _fake_message(user_id=1)
    msg_b = _fake_message(user_id=2)

    async def handler(_event, _data):
        return "ok"

    async def run() -> list:
        return [
            await mw(handler, msg_a, {}),
            await mw(handler, msg_b, {}),
            await mw(handler, msg_a, {}),
            await mw(handler, msg_b, {}),
        ]

    out = asyncio.run(run())
    assert out[0] == "ok"
    assert out[1] == "ok"
    assert out[2] is None
    assert out[3] is None


def test_throttle_no_user_passthrough() -> None:
    mw = ThrottleMiddleware(rate=1, per=10.0)

    async def handler(_event, _data):
        return "ok"

    async def run() -> list:
        # No user — should pass through unconditionally
        return [await mw(handler, object(), {}) for _ in range(5)]

    out = asyncio.run(run())
    assert out == ["ok"] * 5
