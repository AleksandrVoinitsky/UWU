"""Семантический поиск по каталогу (pgvector + эмбеддинги) с fallback.

Поиск по смыслу использует векторные представления товаров (``pgvector``) и
OpenAI-совместимый провайдер эмбеддингов. Если провайдер не настроен или таблица
эмбеддингов пуста — выполняется fallback по ключевым словам (ILIKE), чтобы
функция оставалась работоспособной.

См. также: :mod:`app.models.embeddings`, :mod:`app.services.embedding_service`,
:mod:`app.services.stock_service`, :mod:`app.api.agent`.
"""
from __future__ import annotations

import re

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.catalog import Nomenklatura
from app.models.embeddings import EMBEDDING_DIM, NomenklaturaEmbedding
from app.services import embedding_service, stock_service

logger = get_logger("app.search")

# Размер батча при пересборке эмбеддингов каталога.
_EMBED_BATCH = 32


def build_nomenklatura_text(nomen: Nomenklatura) -> str:
    """Текст для эмбеддинга: наименование + полное наименование + артикул."""
    parts = [nomen.name]
    if nomen.full_name:
        parts.append(nomen.full_name)
    if nomen.artikul:
        parts.append(nomen.artikul)
    return " ".join(parts).strip()


async def _product(nomen: Nomenklatura, session: AsyncSession, *, similarity: float | None = None) -> dict:
    """Представление товара для ответа (остаток + цена)."""
    stock = await stock_service.get_balance(session, nomen.id)
    out: dict = {
        "id": nomen.id,
        "name": nomen.name,
        "full_name": nomen.full_name,
        "artikul": nomen.artikul,
        "price": str(nomen.retail_price) if nomen.retail_price is not None else None,
        "stock": str(stock),
    }
    if similarity is not None:
        out["similarity"] = round(similarity, 4)
    return out


def _search_terms(query: str) -> list[str]:
    """Разбивает запрос на значимые токены (буквы/цифры, ≥2 символа, без регистра)."""
    return [
        t for t in re.findall(r"[a-zа-яё0-9]+", (query or "").lower()) if len(t) >= 2
    ]


async def keyword_search(session: AsyncSession, query: str, limit: int = 50) -> list[dict]:
    """Поиск товаров по ключевым словам (ILIKE по названию/артикулу).

    Запрос токенизируется, и каждая позиция ищется по любому из токенов (OR) —
    так фразы вида «хлеб пшеничный» находят «Хлеб пшеничный нарезной», а не
    только точные подстроки. Токены короче двух символов игнорируются.
    """
    terms = _search_terms(query)
    if not terms:
        return []
    conditions = [
        or_(
            Nomenklatura.name.ilike(f"%{t}%"),
            Nomenklatura.artikul.ilike(f"%{t}%"),
        )
        for t in terms
    ]
    # Релевантность: совпадение по началу названия (префикс) важнее, чем по
    # подстроке в середине. Иначе короткий запрос «сок» находит «Сахар-песок»
    # (в слове «песок» есть «сок») раньше, чем «Сок апельсиновый» — и create_order
    # с limit=1 подставляет не тот товар.
    prefix = or_(*[Nomenklatura.name.ilike(f"{t}%") for t in terms])
    relevance = case((prefix, 0), else_=1)
    result = await session.execute(
        select(Nomenklatura)
        .where(or_(*conditions))
        .order_by(relevance, Nomenklatura.name)
        .limit(limit)
    )
    return [await _product(n, session) for n in result.scalars()]


async def _has_embeddings(session: AsyncSession) -> bool:
    """Есть ли хотя бы один эмбеддинг в таблице."""
    result = await session.execute(select(NomenklaturaEmbedding.id).limit(1))
    return result.scalar_one_or_none() is not None


async def embeddings_status(session: AsyncSession) -> dict:
    """Статус семантического поиска: настроен ли провайдер и сколько эмбеддингов."""
    count = (
        await session.execute(select(func.count(NomenklaturaEmbedding.id)))
    ).scalar_one()
    total = (await session.execute(select(func.count(Nomenklatura.id)))).scalar_one()
    return {
        "configured": embedding_service.is_configured(),
        "count": int(count or 0),
        "total": int(total or 0),
    }


async def search_semantic(session: AsyncSession, query: str, limit: int = 10) -> list[dict]:
    """Поиск товаров по смыслу; при недоступности эмбеддингов — fallback ILIKE.

    Порядок предпочтения:
    1. Векторный поиск (косинусное сходство), если провайдер настроен и есть
       готовые эмбеддинги;
    2. Fallback — поиск по ключевым словам.
    """
    if embedding_service.is_configured() and await _has_embeddings(session):
        try:
            vectors = await embedding_service.embed_texts([query])
            query_vec = vectors[0]
            if len(query_vec) != EMBEDDING_DIM:
                logger.warning(
                    "Embedding dim %d != column dim %d; fallback to keyword",
                    len(query_vec),
                    EMBEDDING_DIM,
                )
            else:
                return await _vector_search(session, query_vec, limit)
        except embedding_service.EmbeddingError as exc:
            logger.warning("Semantic search unavailable (%s); fallback to keyword", exc)
    return await keyword_search(session, query, limit)


async def _vector_search(session: AsyncSession, query_vec: list[float], limit: int) -> list[dict]:
    """Косинусный поиск ближайших эмбеддингов номенклатуры."""
    result = await session.execute(
        select(Nomenklatura, NomenklaturaEmbedding.embedding.cosine_distance(query_vec))
        .join(Nomenklatura, Nomenklatura.id == NomenklaturaEmbedding.nomenklatura_id)
        .order_by(NomenklaturaEmbedding.embedding.cosine_distance(query_vec))
        .limit(limit)
    )
    out: list[dict] = []
    for nomen, distance in result.all():
        similarity = 1.0 - float(distance)
        out.append(await _product(nomen, session, similarity=similarity))
    return out


async def rebuild_embeddings(session: AsyncSession) -> int:
    """Пересобирает эмбеддинги всей номенклатуры. Возвращает число обработанных позиций.

    Вызывается из админки (кнопка «Пересобрать эмбеддинги») или вручную.
    Существующие эмбеддинги перезаписываются.
    """
    if not embedding_service.is_configured():
        raise embedding_service.EmbeddingError("Embedding provider is not configured")

    nomen_list = list((await session.execute(select(Nomenklatura).order_by(Nomenklatura.id))).scalars())
    if not nomen_list:
        return 0

    client = embedding_service.get_client()
    count = 0
    for start in range(0, len(nomen_list), _EMBED_BATCH):
        batch = nomen_list[start : start + _EMBED_BATCH]
        texts = [build_nomenklatura_text(n) for n in batch]
        vectors = await client.embed_texts(texts)
        for nomen, text, vec in zip(batch, texts, vectors):
            if len(vec) != EMBEDDING_DIM:
                raise embedding_service.EmbeddingError(
                    f"Embedding dim {len(vec)} != {EMBEDDING_DIM} for nomenklatura #{nomen.id}"
                )
            existing = (
                await session.execute(
                    select(NomenklaturaEmbedding).where(
                        NomenklaturaEmbedding.nomenklatura_id == nomen.id
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    NomenklaturaEmbedding(
                        nomenklatura_id=nomen.id, text=text, embedding=vec
                    )
                )
            else:
                existing.text = text
                existing.embedding = vec
            count += 1
        await session.commit()
    return count
