"""Accessibility helpers: «plain text» mode без эмодзи и HTML.

Сценарий: пользователь с дислексией / голосовой читалкой включает
``/accessibility`` → бот переключает рендер на чистый текст. Лучше
ли это OpenDyslexic-шрифта в реальной жизни — отдельный вопрос, но
плагин-эмодзи и обилие <b> в реалных скрин-ридерах звучит ужасно.
"""

from __future__ import annotations

import re

_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_EMOJI = re.compile(
    "["
    "\U0001f100-\U0001f1ff"  # enclosed alphanumeric (🆘 etc.)
    "\U0001f200-\U0001f2ff"
    "\U0001f300-\U0001fad0"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f900-\U0001f9ff"
    "\U0001fa70-\U0001faff"
    "\u2600-\u27bf"
    "\u2300-\u23ff"
    "]",
    flags=re.UNICODE,
)


def plain_text(html: str) -> str:
    """Strip emoji + HTML tags + collapse repeated whitespace."""
    no_tags = _HTML_TAG.sub("", html)
    no_emoji = _EMOJI.sub("", no_tags)
    no_emoji = no_emoji.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    cleaned = re.sub(r"[ \t]+", " ", no_emoji)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def render(html: str, *, accessibility: bool) -> str:
    """If accessibility is enabled — return plain text; else passthrough."""
    return plain_text(html) if accessibility else html
