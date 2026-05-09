"""GigaChat Vision: триаж по фотографии раны/ожога/состояния (C2).

ВАЖНО: это **не диагноз**. Сценарий — пользователь фотографирует ситуацию,
LLM возвращает категорию + рекомендованный сценарий из 30. В любом
неоднозначном случае — звонок 112.

Используется тот же ``GIGACHAT_API_KEY`` (scope ``GIGACHAT_API_PERS``),
что и в ``bot/llm.py``. Модель — ``GigaChat-2-Pro``, поддерживает image input.

Включается, только если в окружении есть ``GIGACHAT_API_KEY``. Если ключа
нет — модуль возвращает ``None`` и хендлер вежливо отвечает «выключено».
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

import aiohttp

from bot.llm import _get_gigachat_access_token, _gigachat_ssl_context

log = logging.getLogger("spas.vision")

_GIGACHAT_FILES_URL = "https://gigachat.devices.sberbank.ru/api/v1/files"
_GIGACHAT_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

_DEFAULT_MODEL = os.getenv("GIGACHAT_VISION_MODEL", "GigaChat-2-Pro")

# In-memory rate limit: 5 фото/час/user (vision ощутимо дороже текста).
_VISION_RATE = 5
_VISION_WINDOW_SEC = 3600.0
_user_history: dict[int, deque[float]] = defaultdict(deque)


VISION_SYSTEM_PROMPT = """\
Ты — справочный AI-помощник «СПАС» по первой помощи для подростков 14–17 лет.
Тебе прислали фотографию. Не давай диагноз. Твоя задача:

1. Определить категорию: одна из {burn, bleeding, fracture, animal_bite,
   choking_visible, allergy_rash, abrasion, unknown}.
2. Определить степень тревожности: low / mid / high.
3. Если есть угроза жизни (артериальное кровотечение, обширный ожог 2-3 ст.,
   признаки анафилаксии, бессознательный человек) — поставить severity=high
   и в ответе первым словом написать "ПОЗВОНИ 112 СЕЙЧАС".
4. Назвать ОДИН id сценария из списка: ozhog, krovotechenie_arterialnoe,
   krovotechenie_venoznoe, perelom, anafilaksiya, ukus_zhivotnogo, ssadina,
   syp_allergiya, udushe, obmorok. Если не уверен — id=unknown.
5. Ответить СТРОГО валидным JSON без префиксов и пояснений в формате:

{"category": "...", "severity": "low|mid|high", "scenario_id": "...", "advice": "1-2 предложения"}

Не используй markdown, не оборачивай в ```json. Всегда заканчивай advice
напоминанием "При сомнении — звони 112"."""


@dataclass
class VisionResult:
    category: str
    severity: str
    scenario_id: str
    advice: str


def vision_enabled() -> bool:
    return bool(os.getenv("GIGACHAT_API_KEY"))


def _hit_rate_limit(user_id: int) -> bool:
    now = time.monotonic()
    history = _user_history[user_id]
    while history and now - history[0] > _VISION_WINDOW_SEC:
        history.popleft()
    if len(history) >= _VISION_RATE:
        return True
    history.append(now)
    return False


def _release_rate_slot(user_id: int) -> None:
    history = _user_history[user_id]
    if history:
        history.pop()


async def upload_image(image_bytes: bytes, filename: str = "photo.jpg") -> str | None:
    """Upload image to /api/v1/files. Returns ``id`` or None on failure."""
    if not vision_enabled():
        return None
    try:
        token = await _get_gigachat_access_token()
    except Exception as exc:
        log.warning("vision oauth failed: %s", exc)
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "RqUID": str(uuid.uuid4()),
        "Accept": "application/json",
    }
    form = aiohttp.FormData()
    form.add_field("file", image_bytes, filename=filename, content_type="image/jpeg")
    form.add_field("purpose", "general")
    ssl_ctx = _gigachat_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is not None else None
    try:
        async with (
            aiohttp.ClientSession(connector=connector) as s,
            s.post(
                _GIGACHAT_FILES_URL,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r,
        ):
            r.raise_for_status()
            data = await r.json()
            return str(data.get("id") or data.get("file_id") or "") or None
    except Exception as exc:
        log.warning("vision upload failed: %s", exc)
        return None


async def analyse_photo(file_id: str) -> VisionResult | None:
    """Send the uploaded file to chat-completions for triage. Returns None on error."""
    if not vision_enabled():
        return None
    try:
        token = await _get_gigachat_access_token()
    except Exception as exc:
        log.warning("vision oauth failed: %s", exc)
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": _DEFAULT_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Опиши, что ты видишь на фото.",
                "attachments": [file_id],
            },
        ],
    }
    ssl_ctx = _gigachat_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is not None else None
    try:
        async with (
            aiohttp.ClientSession(connector=connector) as s,
            s.post(
                _GIGACHAT_CHAT_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r,
        ):
            r.raise_for_status()
            data = await r.json()
    except Exception as exc:
        log.warning("vision chat failed: %s", exc)
        return None

    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return VisionResult(
            category=str(parsed.get("category", "unknown")),
            severity=str(parsed.get("severity", "mid")),
            scenario_id=str(parsed.get("scenario_id", "unknown")),
            advice=str(parsed.get("advice", "При сомнении — звони 112")),
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        log.warning("vision parse failed: %s; raw=%r", exc, data)
        return None


async def triage_photo(image_bytes: bytes, *, user_id: int) -> VisionResult | str | None:
    """High-level entry point: rate-limit + upload + analyse.

    Returns:
        VisionResult on success.
        "rate_limit" if the user has exceeded 5 photos / hour.
        None on any other failure (network, JSON, missing key).
    """
    if not vision_enabled():
        return None
    if _hit_rate_limit(user_id):
        return "rate_limit"
    try:
        file_id = await upload_image(image_bytes)
        if not file_id:
            _release_rate_slot(user_id)
            return None
        return await analyse_photo(file_id)
    except asyncio.CancelledError:
        _release_rate_slot(user_id)
        raise
