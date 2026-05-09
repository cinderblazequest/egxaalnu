"""Per-user rate limiter for aiogram updates.

Sliding window in memory: max ``rate`` events per ``per`` seconds, per
user_id. Excess updates are silently dropped (the user just sees no
reply for the throttled action). This is enough to protect the bot
from a flood / accidental key spam in panic; a determined attacker
would still need a real Telegram account.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

log = logging.getLogger("spas.middleware.throttle")


class ThrottleMiddleware(BaseMiddleware):
    """Allow up to ``rate`` events per ``per`` seconds per user."""

    def __init__(self, rate: int = 5, per: float = 1.0) -> None:
        self.rate = rate
        self.per = per
        self._buckets: dict[int, deque[float]] = {}

    def _user_id(self, event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = self._user_id(event)
        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._buckets.setdefault(user_id, deque())
        cutoff = now - self.per
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.rate:
            log.info("throttled user_id=%s rate=%d per=%.1fs", user_id, self.rate, self.per)
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком быстро — подожди секунду.", show_alert=False)
            return None

        bucket.append(now)
        return await handler(event, data)
