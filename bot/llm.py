"""
Опциональный LLM-слой для свободных вопросов пользователя.

Поддерживается:
- GigaChat (Сбер) — эндпоинт https://gigachat.devices.sberbank.ru/api/v1/chat/completions
- YandexGPT — эндпоинт https://llm.api.cloud.yandex.net/foundationModels/v1/completion

Если ключи не заданы — бот сам отвечает «свободные вопросы пока не доступны,
выберите сценарий из меню».
"""

from __future__ import annotations

import logging
import os
import ssl
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger("spas.llm")

_RUSSIAN_CA_BUNDLE = Path(__file__).resolve().parent.parent / "ssl" / "russian_trusted_bundle.pem"

_GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GIGACHAT_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

_gigachat_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def _gigachat_ssl_context() -> ssl.SSLContext | None:
    """Build an SSL context that trusts the Russian Trusted Root + Sub CA.

    GigaChat is served behind a TLS chain signed by the Russian Trusted CA,
    which is not in the system trust store on most Linux/macOS distributions.
    The CA bundle is shipped in `ssl/russian_trusted_bundle.pem` and loaded
    here so the bot works out of the box.
    """
    if not _RUSSIAN_CA_BUNDLE.is_file():
        log.warning("Russian Trusted CA bundle missing at %s", _RUSSIAN_CA_BUNDLE)
        return None
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(_RUSSIAN_CA_BUNDLE))
    return ctx


async def _get_gigachat_access_token() -> str:
    """Exchange the GIGACHAT_API_KEY (Basic auth) for a short-lived access token.

    The Auth key issued by Sber is a base64 of `client_id:client_secret`. To call
    the chat-completions API we must first POST it to the OAuth endpoint and
    receive an access token (~30 min TTL). The token is cached module-level.
    """
    now = time.time()
    cached = _gigachat_token_cache
    if cached["access_token"] and cached["expires_at"] - 60 > now:
        return str(cached["access_token"])

    auth_key = os.environ["GIGACHAT_API_KEY"]
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    headers = {
        "Authorization": f"Basic {auth_key}",
        "RqUID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    body = {"scope": scope}
    ssl_ctx = _gigachat_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is not None else None
    async with (
        aiohttp.ClientSession(connector=connector) as s,
        s.post(
            _GIGACHAT_OAUTH_URL,
            data=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r,
    ):
        r.raise_for_status()
        data = await r.json()
    access_token = str(data["access_token"])
    expires_at_ms = float(data.get("expires_at", (now + 1500) * 1000))
    cached["access_token"] = access_token
    cached["expires_at"] = expires_at_ms / 1000.0
    return access_token


SYSTEM_PROMPT = """\
Ты — справочный AI-помощник «СПАС» для подростков 14-17 лет в России.
Ты помогаешь сориентироваться в ситуации первой помощи и подсказываешь,
какой сценарий из меню бота открыть. Ты НЕ ставишь диагнозов и НЕ
заменяешь скорую помощь.

Правила:
1. ВСЕГДА в первую очередь рекомендуй позвонить 112 или 103 при любой
   опасной ситуации.
2. Отвечай коротко: 4-6 предложений, простым языком.
3. Если ситуация критическая — говори в начале: "ПОЗВОНИ 112 СЕЙЧАС".
4. Опирайся на стандарты Российского Национального Совета по реанимации
   и ERC Guidelines.
5. Не давай дозировок лекарств, кроме общеизвестных безрецептурных
   (парацетамол, ибупрофен, аспирин при инфаркте 250-500 мг).
6. Если вопрос НЕ про первую помощь — мягко верни в тему.
7. Заканчивай ответ кнопкой действия: какой сценарий открыть в боте."""


async def ask_llm(question: str) -> str | None:
    """Вернёт ответ LLM или None, если ни один провайдер не настроен/доступен."""
    if os.getenv("GIGACHAT_API_KEY"):
        try:
            return await _ask_gigachat(question)
        except Exception as exc:
            log.warning("GigaChat failed: %s", exc)

    if os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID"):
        try:
            return await _ask_yandex(question)
        except Exception as exc:
            log.warning("YandexGPT failed: %s", exc)

    return None


async def _ask_gigachat(question: str) -> str:
    access_token = await _get_gigachat_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload: dict[str, Any] = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    ssl_ctx = _gigachat_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is not None else None
    async with (
        aiohttp.ClientSession(connector=connector) as s,
        s.post(
            _GIGACHAT_CHAT_URL,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r,
    ):
        r.raise_for_status()
        data = await r.json()
        return data["choices"][0]["message"]["content"]


async def _ask_yandex(question: str) -> str:
    api_key = os.environ["YANDEX_API_KEY"]
    folder = os.environ["YANDEX_FOLDER_ID"]
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "modelUri": f"gpt://{folder}/yandexgpt-lite",
        "completionOptions": {"temperature": 0.2, "maxTokens": 400},
        "messages": [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": question},
        ],
    }
    async with (
        aiohttp.ClientSession() as s,
        s.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r,
    ):
        r.raise_for_status()
        data = await r.json()
        return data["result"]["alternatives"][0]["message"]["text"]
