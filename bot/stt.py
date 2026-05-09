"""Speech-to-text via Yandex SpeechKit (опционально).

Когда задан ``YANDEX_STT_API_KEY`` — мы конвертим присланный voice в
текст и подаём его как обычный свободный вопрос. Без ключа — просим
текстом.

Yandex SpeechKit short audio recognition:
  POST https://stt.api.cloud.yandex.net/speech/v1/stt:recognize
  ?lang=ru-RU&format=oggopus&sampleRateHertz=48000&topic=general
  Header: Authorization: Api-Key <key>
  Body: бинарный аудио ≤ 1 Мб, ≤ 30 секунд
"""

from __future__ import annotations

import logging
import os

import aiohttp

log = logging.getLogger("spas.stt")


YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"


def stt_enabled() -> bool:
    return bool(os.getenv("YANDEX_STT_API_KEY"))


async def transcribe_ogg(audio_bytes: bytes, *, lang: str = "ru-RU") -> str | None:
    """Recognize ogg-opus voice (Telegram default). Returns text or None."""
    api_key = os.getenv("YANDEX_STT_API_KEY")
    if not api_key:
        return None
    folder_id = os.getenv("YANDEX_STT_FOLDER_ID") or os.getenv("YANDEX_FOLDER_ID")
    params = {
        "lang": lang,
        "format": "oggopus",
        "sampleRateHertz": "48000",
        "topic": "general",
    }
    if folder_id:
        params["folderId"] = folder_id
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "audio/ogg",
    }
    try:
        async with (
            aiohttp.ClientSession() as s,
            s.post(
                YANDEX_STT_URL,
                params=params,
                data=audio_bytes,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r,
        ):
            if r.status != 200:
                body = await r.text()
                log.warning("yandex stt http %d: %s", r.status, body[:200])
                return None
            data = await r.json()
            return data.get("result") or None
    except Exception as exc:
        log.warning("yandex stt failed: %s", exc)
        return None
