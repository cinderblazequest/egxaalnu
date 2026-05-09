"""Yandex SpeechKit TTS — озвучка шагов сценариев (A3).

Активируется только если есть ``YANDEX_API_KEY`` И SA с ролью
``ai.speechkit-tts.user``. Иначе модуль возвращает ``None`` и хендлер
сообщает «озвучка отключена».

Кэширование: ответ SpeechKit (OGG Opus) сохраняется в локальной директории
``./audio/cache/{sha1(text+voice)}.ogg`` — это позволяет не платить за один
и тот же шаг дважды.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import aiohttp

log = logging.getLogger("spas.tts")

_TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = ROOT / "audio" / "cache"


def tts_enabled() -> bool:
    return bool(os.getenv("YANDEX_API_KEY"))


def _cache_key(text: str, voice: str) -> Path:
    h = hashlib.sha1(f"{voice}:{text}".encode()).hexdigest()
    return _CACHE_DIR / f"{h}.ogg"


async def synthesize(text: str, *, voice: str = "oksana", speed: float = 1.0) -> bytes | None:
    """Synthesize ``text`` to OGG Opus bytes. Returns None on error/disabled.

    Voice options: ``oksana``, ``ermil``, ``alyss``, ``zahar`` (Yandex SpeechKit v1).
    """
    if not tts_enabled():
        return None
    if not text.strip():
        return None
    text = text.strip()[:5000]  # SpeechKit hard limit per request

    cache = _cache_key(text, voice)
    if cache.is_file():
        try:
            return cache.read_bytes()
        except OSError as exc:
            log.warning("tts cache read failed: %s", exc)

    api_key = os.environ["YANDEX_API_KEY"]
    folder_id = os.getenv("YANDEX_FOLDER_ID", "")
    headers = {"Authorization": f"Api-Key {api_key}"}
    data: dict[str, str] = {
        "text": text,
        "lang": "ru-RU",
        "voice": voice,
        "format": "oggopus",
        "speed": f"{speed:.2f}",
    }
    if folder_id:
        data["folderId"] = folder_id

    try:
        async with (
            aiohttp.ClientSession() as s,
            s.post(_TTS_URL, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=20)) as r,
        ):
            if r.status != 200:
                body = await r.text()
                log.warning("tts http %s: %s", r.status, body[:200])
                return None
            audio = await r.read()
    except Exception as exc:
        log.warning("tts request failed: %s", exc)
        return None

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(audio)
    except OSError as exc:
        log.warning("tts cache write failed: %s", exc)
    return audio
