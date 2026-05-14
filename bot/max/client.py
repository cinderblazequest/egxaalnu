"""Тонкий async-клиент Max Bot API (`platform-api.max.ru`).

API совместим с TamTam Bot API (Max — это переименованный мессенджер от
VK на базе TamTam). Документация: https://dev.max.ru/, OpenAPI:
https://maxmessengerapi.ru/max-bot-api-openapi-fixed.json.

Модель:
- HTTPS-запросы к `https://platform-api.max.ru` с query-параметром
  `access_token=<TOKEN>`;
- long-polling через ``GET /updates?marker=&types=&timeout=``;
- отправка через ``POST /messages?chat_id=<id>``;
- inline-клавиатура передаётся как `attachment` типа `inline_keyboard`.

Этот клиент покрывает только то, что нужно ботy СПАС: получить апдейты,
послать сообщение (с/без клавиатуры), отметить callback. Он намеренно
маленький — без зависимостей кроме aiohttp (который и так в проекте).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

log = logging.getLogger("spas.max")

DEFAULT_BASE_URL = "https://platform-api.max.ru"


@dataclass
class MaxButton:
    """Inline-кнопка Max API (тип ``callback`` или ``link``)."""

    text: str
    payload: str | None = None
    url: str | None = None

    def to_api(self) -> dict[str, Any]:
        if self.url:
            return {"type": "link", "text": self.text, "url": self.url}
        return {"type": "callback", "text": self.text, "payload": self.payload or self.text}


def keyboard(rows: list[list[MaxButton]]) -> dict[str, Any]:
    """Собрать payload `attachment` типа inline_keyboard."""
    return {
        "type": "inline_keyboard",
        "payload": {"buttons": [[b.to_api() for b in row] for row in rows]},
    }


class MaxAPIError(RuntimeError):
    """Ошибка обращения к Max Bot API."""

    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"Max API {status}: {body!r}")
        self.status = status
        self.body = body


class MaxBotClient:
    """Минимальный клиент Max Bot API."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        if not token:
            raise ValueError("MAX_BOT_TOKEN не задан")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> MaxBotClient:
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._session is None:  # pragma: no cover — защита от неправильного использования
            raise RuntimeError("MaxBotClient должен использоваться как async-context")
        all_params = {"access_token": self._token}
        if params:
            all_params.update({k: v for k, v in params.items() if v is not None})
        url = self._base_url + path
        async with self._session.request(method, url, params=all_params, json=json) as resp:
            try:
                body = await resp.json()
            except aiohttp.ContentTypeError:
                body = await resp.text()
            if resp.status >= 400:
                raise MaxAPIError(resp.status, body)
            return body  # type: ignore[no-any-return]

    async def get_me(self) -> dict[str, Any]:
        """``GET /me`` — информация о боте (``user_id``, ``name``, ``username``)."""
        return await self._request("GET", "/me")

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        timeout: int = 30,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Long-polling через ``GET /updates``.

        Возвращает ``{"updates": [...], "marker": <next>}``. Передавайте
        ``marker`` следующего вызова, чтобы не получать повторно.
        """
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        return await self._request("GET", "/updates", params=params)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[MaxButton]] | None = None,
        disable_link_preview: bool = False,
        notify: bool = True,
    ) -> dict[str, Any]:
        """``POST /messages`` — текст с опциональной inline-клавиатурой."""
        body: dict[str, Any] = {"text": text, "notify": notify}
        if buttons:
            body["attachments"] = [keyboard(buttons)]
        return await self._request(
            "POST",
            "/messages",
            params={"chat_id": chat_id, "disable_link_preview": str(disable_link_preview).lower()},
            json=body,
        )

    async def answer_callback(self, callback_id: str, *, notification: str | None = None) -> dict[str, Any]:
        """``POST /answers`` — подтвердить callback (необязательно, но снимает «загрузку» в UI)."""
        body: dict[str, Any] = {}
        if notification is not None:
            body["notification"] = notification
        return await self._request("POST", "/answers", params={"callback_id": callback_id}, json=body)
