"""Tiny aiohttp /health server used as a Fly.io / k8s liveness probe.

Runs alongside the aiogram polling loop. Emits:
- GET /health  -> 200 {"ok": true, ...}
- GET /metrics -> 200 plain text Prometheus-style counters (DAU, etc).

Bind address comes from HEALTH_HOST (default ``0.0.0.0``) and HEALTH_PORT
(default ``8080``). If HEALTH_PORT is ``0`` or ``off`` the server is
not started.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from bot.storage import Storage

log = logging.getLogger("spas.health")


async def _health(request: web.Request) -> web.Response:
    storage: Storage | None = request.app.get("storage")
    ok = True
    db_ok = False
    if storage is not None:
        try:
            await storage.db.execute("SELECT 1")
            db_ok = True
        except Exception as exc:
            log.warning("health: db check failed: %s", exc)
            ok = False
    return web.json_response(
        {"ok": ok, "db": db_ok, "version": os.getenv("APP_VERSION", "dev")},
        status=200 if ok else 503,
    )


async def _metrics(request: web.Request) -> web.Response:
    storage: Storage | None = request.app.get("storage")
    if storage is None:
        return web.Response(text="# storage not ready\n", content_type="text/plain")
    try:
        m = await storage.metrics()
    except Exception as exc:
        log.warning("metrics fetch failed: %s", exc)
        return web.Response(text=f"# error: {exc}\n", content_type="text/plain", status=500)
    lines = [
        f"spas_users_total {m['users_total']}",
        f"spas_dau {m['dau']}",
        f"spas_scenarios_completed {m['scenarios_completed']}",
        f"spas_avg_nps {m['avg_nps']:.2f}",
    ]
    if m.get("pre_score_avg") is not None:
        lines.append(f"spas_pre_score_avg {m['pre_score_avg']:.4f}")
    if m.get("post_score_avg") is not None:
        lines.append(f"spas_post_score_avg {m['post_score_avg']:.4f}")
    return web.Response(text="\n".join(lines) + "\n", content_type="text/plain")


def build_app(storage: Storage | None = None) -> web.Application:
    app = web.Application()
    app["storage"] = storage
    app.router.add_get("/health", _health)
    app.router.add_get("/metrics", _metrics)
    return app


async def start_health_server(storage: Storage | None = None) -> web.AppRunner | None:
    """Start the /health webserver in the background. Returns the runner so the
    caller can call ``await runner.cleanup()`` on shutdown.
    """
    raw_port = os.getenv("HEALTH_PORT", "8080")
    if raw_port.lower() in {"0", "off", "false", ""}:
        log.info("health server disabled via HEALTH_PORT")
        return None
    try:
        port = int(raw_port)
    except ValueError:
        log.warning("invalid HEALTH_PORT=%r, defaulting to 8080", raw_port)
        port = 8080
    host = os.getenv("HEALTH_HOST", "0.0.0.0")
    app = build_app(storage)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
    except OSError as exc:
        log.warning("health server bind failed on %s:%s: %s", host, port, exc)
        await runner.cleanup()
        return None
    log.info("health server on http://%s:%d/health", host, port)
    return runner


async def shutdown_runner(runner: web.AppRunner | None) -> None:
    if runner is None:
        return
    try:
        await asyncio.wait_for(runner.cleanup(), timeout=5)
    except (TimeoutError, Exception) as exc:
        log.debug("health runner cleanup error: %s", exc)
