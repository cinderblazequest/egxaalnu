"""Logging configuration for СПАС.

By default uses a human-friendly format. Set ``LOG_FORMAT=json`` to emit
JSON lines (useful for Loki / Datadog / Sentry parsing on Fly.io).

Set ``SENTRY_DSN`` to also send WARNING+ to Sentry. Sentry SDK is optional
— if it's not installed, the logger keeps working without it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Compact JSON line per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for extra in ("user_id", "scenario_id", "event"):
            value = record.__dict__.get(extra)
            if value is not None:
                payload[extra] = value
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """Configure root logger from env: LOG_LEVEL, LOG_FORMAT, SENTRY_DSN."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = os.getenv("LOG_FORMAT", "human").lower()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    _maybe_setup_sentry()


def _maybe_setup_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                LoggingIntegration(level=logging.INFO, event_level=logging.WARNING),
            ],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.0")),
            release=os.getenv("SENTRY_RELEASE"),
            environment=os.getenv("SENTRY_ENV", "production"),
        )
        logging.getLogger("spas").info("Sentry enabled")
    except ImportError:
        logging.getLogger("spas").warning(
            "SENTRY_DSN set but sentry-sdk not installed; pip install sentry-sdk"
        )
