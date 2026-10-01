"""Абстракция LLM (OpenAI-совместимый API).

Подключаемый провайдер: ``base_url`` + ``api_key`` + ``model`` из конфига.
Если ключ не задан — ``LLM.available`` возвращает ``False`` и агент использует
детерминированный fallback (:mod:`app.responder`). Сам SDK импортируется лениво,
чтобы сервис стартовал и без установленного/валидного провайдера.

См. также: :mod:`app.config`, :mod:`app.responder`.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger("app.llm")


class LLM:
    """Тонкая обёртка над OpenAI-совместимым API (async)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        """LLM доступен, только если задан API-ключ (иначе fallback)."""
        return bool(self.api_key)

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("openai package is not installed") from exc
            self._client = AsyncOpenAI(
                base_url=self.base_url or None,
                api_key=self.api_key,
                timeout=settings.llm_timeout,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Возвращает текст ответа LLM на список сообщений (роли/содержимое)."""
        client = self._ensure_client()
        resp = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            max_tokens=max_tokens if max_tokens is not None else settings.llm_max_tokens,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()

    async def classify(self, text: str) -> str:
        """Классифицирует намерение сообщения в одну из категорий графа."""
        try:
            answer = await self.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Классифицируй сообщение покупателя в одну категорию: "
                            "consultation, stock, price, order_status, add_to_cart, "
                            "create_order, reorder_suggestion, fallback. "
                            "Ответ — только одно слово (название категории)."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0.0,
                max_tokens=16,
            )
            return answer.strip().lower()
        except Exception as exc:  # noqa: BLE001 — сеть/провайдер не должны ронять агента
            logger.warning("LLM classify failed: %s", exc)
            return "fallback"

    async def extract_search_query(self, text: str) -> str:
        """Извлекает из сообщения короткий поисковый запрос (ключевые слова товара).

        Нужен, чтобы искать в каталоге по сути («посоветуй что-нибудь из
        молочных продуктов» → «молоко»), а не по всему тексту с приветствиями.
        Возвращает пустую строку, если товар/категория не упомянуты.
        """
        try:
            answer = await self.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Извлеки из сообщения покупателя конкретные названия или "
                            "виды товаров для поиска в каталоге, в именительном падеже "
                            "единственного числа. Обобщение раскрывай в примеры товаров: "
                            "«молочные продукты» → «молоко кефир творог сыр», "
                            "«напитки» → «сок вода чай». Ответь только этими словами "
                            "(1-4 слова) через пробел, без пояснений и знаков препинания. "
                            "Если товар или категория не упомянуты — ответь пустой строкой."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0.0,
                max_tokens=40,
            )
            return " ".join(answer.strip().split())
        except Exception as exc:  # noqa: BLE001 — сеть/провайдер не должны ронять агента
            logger.warning("LLM extract_search_query failed: %s", exc)
            return ""
