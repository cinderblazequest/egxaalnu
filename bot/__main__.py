"""
СПАС: AI-помощник первой помощи — Telegram bot.
Точка входа.

Поддерживает два режима работы:
- polling (по умолчанию) — `WEBHOOK_MODE=0`, бот сам опрашивает Telegram;
- webhook — `WEBHOOK_MODE=1`, поднимаем aiohttp на ``WEBHOOK_PORT`` и
  регистрируем ``WEBHOOK_URL`` (с секретом ``WEBHOOK_SECRET``).
В обоих режимах:
- стартует health-сервер на ``HEALTH_PORT`` (для Fly.io / k8s liveness),
- по SIGTERM/SIGINT останавливаются: poller/webhook, RSS-таска, health-сервер.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from bot.handlers import register_handlers
from bot.health import shutdown_runner, start_health_server
from bot.log_setup import setup_logging
from bot.mchs_rss import poll_loop as mchs_poll_loop
from bot.middleware import ThrottleMiddleware
from bot.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

setup_logging()
log = logging.getLogger("spas")


async def _start_polling(dp: Dispatcher, bot: Bot, stop: asyncio.Event) -> None:
    """Старт polling-режима, который завершается при ``stop.set()``."""
    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
        name="aiogram-polling",
    )
    try:
        await stop.wait()
    finally:
        await dp.stop_polling()
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await polling_task


async def _start_webhook(dp: Dispatcher, bot: Bot, stop: asyncio.Event) -> None:
    """Старт webhook-режима через aiohttp.

    Конфиг:
      WEBHOOK_URL — публичный HTTPS URL (Fly.io: https://<app>.fly.dev/tg).
      WEBHOOK_SECRET — секрет, который Telegram добавит в заголовок.
      WEBHOOK_PORT — внутренний порт aiohttp (по умолчанию 8443).
    """
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    url = os.getenv("WEBHOOK_URL", "").strip()
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    port = int(os.getenv("WEBHOOK_PORT", "8443"))
    if not url:
        raise RuntimeError("WEBHOOK_MODE=1 требует WEBHOOK_URL")

    app = web.Application()

    async def _healthz(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/healthz", _healthz)

    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret or None).register(app, path="/tg")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    await bot.set_webhook(
        url=url,
        secret_token=secret or None,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    log.info("Webhook включён: %s (порт %s)", url, port)
    try:
        await stop.wait()
    finally:
        with contextlib.suppress(Exception):
            await bot.delete_webhook(drop_pending_updates=False)
        await runner.cleanup()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    """Установить обработчики SIGTERM/SIGINT для graceful-shutdown."""

    def _handler() -> None:
        if not stop.is_set():
            log.info("Получен сигнал — начинаю graceful-shutdown")
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _handler)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN missing in .env")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    throttle_rate = int(os.getenv("THROTTLE_RATE", "5"))
    throttle_per = float(os.getenv("THROTTLE_PER", "1.0"))
    throttle = ThrottleMiddleware(rate=throttle_rate, per=throttle_per)
    dp.message.middleware(throttle)
    dp.callback_query.middleware(throttle)

    storage = Storage(os.getenv("DB_PATH", "spas.db"))
    await storage.init()

    register_handlers(dp, storage=storage, content_dir=ROOT / "content")

    health_runner = await start_health_server(storage)

    rss_task: asyncio.Task[None] | None = None
    if os.getenv("MCHS_RSS_ENABLED", "0") == "1":

        async def _send(uid: int, text: str) -> None:
            try:
                await bot.send_message(uid, text, disable_web_page_preview=False)
            except Exception as exc:
                log.warning("rss send to %s failed: %s", uid, exc)

        interval = float(os.getenv("MCHS_RSS_INTERVAL_SEC", "900"))
        rss_task = asyncio.create_task(
            mchs_poll_loop(storage, _send, interval_sec=interval),
            name="mchs-rss-poll",
        )
        log.info("МЧС RSS поллер включён (interval=%.0fs)", interval)

    me = await bot.get_me()
    log.info("СПАС-бот запущен: @%s", me.username)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, stop)

    webhook_mode = os.getenv("WEBHOOK_MODE", "0") == "1"
    try:
        if webhook_mode:
            await _start_webhook(dp, bot, stop)
        else:
            await _start_polling(dp, bot, stop)
    finally:
        if rss_task is not None:
            rss_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await rss_task
        await shutdown_runner(health_runner)
        await bot.session.close()
        await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
