"""Пересобирает эмбеддинги каталога (семантический поиск, pgvector).

Заполняет таблицу ``nomenklatura_embeddings`` векторными представлениями
текстовых описаний товаров (см. :mod:`app.services.search_service`).

Требует настроенные ``EMBEDDING_BASE_URL`` / ``EMBEDDING_API_KEY`` (OpenAI-
совместимый провайдер эмбеддингов) в окружении/.env.

Запуск (из корня репозитория):

    .venv/Scripts/python scripts/rebuild_embeddings.py
"""
from __future__ import annotations

import asyncio

from app.core.database import async_session_factory
from app.services import search_service


async def main() -> None:
    async with async_session_factory() as session:
        status = await search_service.embeddings_status(session)
        print(f"Провайдер настроен: {status['configured']}")
        print(f"Эмбеддингов в базе: {status['count']} / {status['total']} номенклатуры")
        count = await search_service.rebuild_embeddings(session)
        print(f"OK: пересобрано эмбеддингов — {count}")


if __name__ == "__main__":
    asyncio.run(main())
