"""Точка входа Max-бота СПАС: ``python -m bot.max``.

Конфиг через переменные окружения:
    MAX_BOT_TOKEN — токен от @MasterBot в Max (обязателен).
    MAX_API_BASE — переопределить URL API (по умолчанию platform-api.max.ru).
    LOG_LEVEL — INFO/DEBUG/...
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from pathlib import Path

from dotenv import load_dotenv

from bot.log_setup import setup_logging
from bot.max.client import MaxAPIError, MaxBotClient
from bot.max.handlers import build_context, dispatch_update

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
setup_logging()
log = logging.getLogger("spas.max")


async def run() -> None:
    token = os.getenv("MAX_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MAX_BOT_TOKEN не задан в .env")

    base_url = os.getenv("MAX_API_BASE", "https://platform-api.max.ru")
    ctx = build_context(ROOT / "content")
    log.info("Контент Max-бота загружен: %d сценариев", len(ctx.catalogue.scenarios))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop.set)

    async with MaxBotClient(token, base_url=base_url) as client:
        me = await client.get_me()
        log.info("Max-бот запущен: %s (id=%s)", me.get("name"), me.get("user_id"))
        marker: int | None = None
        while not stop.is_set():
            try:
                payload = await client.get_updates(marker=marker, timeout=30)
            except MaxAPIError as exc:
                log.warning("Max API error %s: %s", exc.status, exc.body)
                await asyncio.sleep(2.0)
                continue
            except Exception as exc:
                log.warning("Сетевая ошибка long-polling: %s", exc)
                await asyncio.sleep(2.0)
                continue
            marker = payload.get("marker") or marker
            for update in payload.get("updates", []) or []:
                try:
                    await dispatch_update(client, ctx, update)
                except Exception:
                    log.exception("Ошибка обработки апдейта: %s", update)
        log.info("Max-бот завершает работу")


if __name__ == "__main__":
    asyncio.run(run())
