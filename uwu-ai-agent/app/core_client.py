"""Тонкий HTTP-клиент к REST API ядра UWU.

Агент НЕ пишет в БД напрямую и не дублирует бизнес-логику — все данные и
действия идут через эндпоинты ``/api/agent/*`` ядра (API-key аутентификация).
Это исключает дрейф бизнес-логики между агентом и интерфейсом.

См. также: :mod:`app.config`, ``app/api/agent.py`` в ядре.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class CoreClientError(RuntimeError):
    """Ошибка обращения к ядру (сеть / неверный ответ / отказ в доступе)."""


class CoreClient:
    """Асинхронный клиент API ядра с API-key аутентификацией."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or settings.core_base_url).rstrip("/")
        self.api_key = api_key or settings.agent_api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-Api-Key": self.api_key} if self.api_key else {},
        )

    async def __aenter__(self) -> "CoreClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Выполняет запрос и возвращает распарсенный JSON (или None для 404)."""
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CoreClientError(f"core request failed: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CoreClientError(
                f"core returned {resp.status_code} on {method} {path}: {resp.text[:300]}"
            )
        if resp.status_code == 204:
            return None
        return resp.json()

    # --- Входящие / исходящие --------------------------------------------------

    async def get_inbox(self) -> list[dict]:
        """Непрочитанные входящие сообщения (polling-режим)."""
        result = await self._request("GET", "/api/agent/inbox")
        return result or []

    async def mark_inbox_read(self, message_ids: list[int]) -> dict | None:
        """Помечает входящие сообщения прочитанными (после обработки)."""
        return await self._request(
            "POST", "/api/agent/inbox/read", json={"message_ids": message_ids}
        )

    async def get_context(self, chat_id: int) -> dict | None:
        """Сводка контекста чата: покупатель, корзина, история сообщений."""
        return await self._request("GET", f"/api/agent/context/{chat_id}")

    async def post_message(self, chat_id: int, text: str) -> dict:
        """Публикует ответ агента в чат (direction="out", author="agent")."""
        return await self._request(
            "POST", "/api/agent/messages", json={"chat_id": chat_id, "text": text}
        )

    async def post_run(self, *, trace_id: str, **fields: Any) -> dict | None:
        """Пишет результат запуска агента в журнал (аудит/трассировка)."""
        payload = {"trace_id": trace_id, **fields}
        try:
            return await self._request("POST", "/api/agent/runs", json=payload)
        except CoreClientError:
            return None

    # --- Инструменты (тонкие обёртки над REST) ----------------------------------

    async def search_catalog(self, query: str, limit: int = 50) -> list[dict]:
        """Поиск товаров по названию/артикулу (с остатком и ценой)."""
        result = await self._request(
            "GET", "/api/agent/search_catalog", params={"query": query}
        )
        return result or []

    async def get_stock(self, nomenklatura_id: int) -> dict | None:
        """Остаток товара (учётный и доступный)."""
        return await self._request(
            "GET", "/api/agent/get_stock", params={"nomenklatura_id": nomenklatura_id}
        )

    async def get_cart(self, customer_id: int) -> dict | None:
        """Текущая корзина покупателя."""
        return await self._request(
            "GET", "/api/agent/get_cart", params={"customer_id": customer_id}
        )

    async def get_order_status(self, order_id: int) -> dict | None:
        """Статус и состав заявки покупателя (ZAKAZ)."""
        return await self._request(
            "GET", "/api/agent/get_zakaz", params={"order_id": order_id}
        )

    async def match_customer(self, phone: str) -> dict:
        """Поиск покупателя/контрагента по номеру телефона."""
        return await self._request(
            "GET", "/api/agent/match_customer", params={"phone": phone}
        )

    async def add_to_cart(
        self, customer_id: int, nomenklatura_id: int, quantity: int
    ) -> dict:
        """Добавляет товар в корзину покупателя (write-tool)."""
        return await self._request(
            "POST",
            "/api/agent/add_to_cart",
            json={
                "customer_id": customer_id,
                "nomenklatura_id": nomenklatura_id,
                "quantity": quantity,
            },
        )

    async def create_order(
        self,
        customer_phone: str,
        items: list[dict],
        customer_name: str | None = None,
    ) -> dict:
        """Создаёт заявку (ZAKAZ) как DRAFT по телефону и списку позиций."""
        return await self._request(
            "POST",
            "/api/agent/create_order",
            json={
                "customer_phone": customer_phone,
                "customer_name": customer_name,
                "items": items,
            },
        )

    async def customer_insights(self, customer_id: int) -> dict | None:
        """Сводка покупателя для персонализации (история/рекомендации/память)."""
        return await self._request("GET", f"/api/agent/customer/{customer_id}")

    # --- Конфигурация (кэш промптов/инструментов) -------------------------------

    async def get_prompts(self) -> list[dict]:
        """Активные промпты (с текстом активной версии)."""
        result = await self._request("GET", "/api/agent/prompts")
        return result or []

    async def get_tools(self) -> list[dict]:
        """Включённые инструменты (реестр)."""
        result = await self._request("GET", "/api/agent/tools")
        return result or []
