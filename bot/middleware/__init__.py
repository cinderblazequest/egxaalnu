"""Bot middleware (throttling, logging, etc)."""

from bot.middleware.throttle import ThrottleMiddleware

__all__ = ["ThrottleMiddleware"]
