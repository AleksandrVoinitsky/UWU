"""Клиент эмбеддингов (OpenAI-совместимый API) для семантического поиска.

Эмбеддинги товаров используются для RAG-поиска по каталогу (``search_semantic``).
Провайдер задаётся конфигурацией (``EMBEDDING_BASE_URL``/``EMBEDDING_API_KEY``/
``EMBEDDING_MODEL``), а не зашит в коде: подходит любой OpenAI-совместимый
бэкенд. Если провайдер не настроен — :func:`is_configured` возвращает ``False``
и семантический поиск переключается на fallback по ключевым словам.

См. также: :mod:`app.services.search_service`, :mod:`app.core.config`.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class EmbeddingError(Exception):
    """Ошибка получения эмбеддингов (не настроен провайдер, сеть или ответ)."""


class EmbeddingClient:
    """Асинхронный клиент OpenAI-совместимого эндпоинта ``/embeddings``."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "text-embedding-3-small",
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
            transport=transport,
        )

    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Возвращает векторы для списка текстов (порядок сохраняется)."""
        if not self.is_configured():
            raise EmbeddingError("Embedding provider is not configured")
        if not texts:
            return []
        try:
            resp = await self._client.post(
                "/embeddings",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Embedding request failed: {exc}") from exc

        data = resp.json()
        embeddings = _extract_embeddings(data)
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Embedding provider returned {len(embeddings)} vectors for {len(texts)} texts"
            )
        return embeddings


def _extract_embeddings(data: Any) -> list[list[float]]:
    """Извлекает векторы из ответа OpenAI-совместимого ``/embeddings``."""
    if isinstance(data, dict) and "data" in data:
        items = data["data"]
    elif isinstance(data, list):
        items = data
    else:
        raise EmbeddingError(f"Unexpected embeddings response: {type(data)!r}")
    out: list[list[float]] = []
    for item in items:
        if isinstance(item, dict):
            vec = item.get("embedding") or item.get("vector")
        else:
            vec = item
        if not isinstance(vec, list):
            raise EmbeddingError("Malformed embedding item (no vector)")
        out.append([float(x) for x in vec])
    return out


# Клиент по умолчанию (настройки из конфигурации). Пересоздаётся при каждом
# вызове :func:`get_client`, чтобы тесты могли подменять transport.
_client: EmbeddingClient | None = None


def get_client() -> EmbeddingClient:
    """Возвращает (и кэширует) клиент эмбеддингов из настроек приложения."""
    global _client
    if _client is None:
        _client = EmbeddingClient(
            settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
    return _client


def is_configured() -> bool:
    return get_client().is_configured()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Возвращает векторы для списка текстов (провайдер из настроек)."""
    return await get_client().embed_texts(texts)
