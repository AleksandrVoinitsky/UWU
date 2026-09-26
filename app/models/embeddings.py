"""Эмбеддинги номенклатуры для семантического поиска (RAG по каталогу).

Векторные представления текстового описания товаров хранятся в PostgreSQL
(расширение ``pgvector``, колонка ``embedding`` типа ``vector``). Используются
эндпоинтом ``POST /api/agent/search_semantic`` для поиска по смыслу (а не только
по точному совпадению ключевых слов).

См. также: :mod:`app.services.search_service`, :mod:`app.services.embedding_service`,
:mod:`app.core.config` (настройки ``embedding_*``).
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin

# Размерность вектора эмбеддингов (совпадает с ``settings.embedding_dim``).
# Смена размерности требует новой миграции (колонка pgvector имеет фиксированный
# размер).
EMBEDDING_DIM = 1536


class NomenklaturaEmbedding(Base, IdMixin, TimestampMixin):
    """Векторное представление одной позиции номенклатуры (1:1)."""

    __tablename__ = "nomenklatura_embeddings"

    nomenklatura_id: Mapped[int] = mapped_column(
        ForeignKey("nomenklatura.id"), unique=True, nullable=False, index=True
    )
    # Исходный текст, по которому строился эмбеддинг (для отладки и пересборки).
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Вектор эмбеддинга (pgvector). Размерность — EMBEDDING_DIM.
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    nomenklatura: Mapped["Nomenklatura"] = relationship()  # noqa: F821
