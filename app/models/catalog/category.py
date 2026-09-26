"""Справочник категорий товаров.

Иерархический справочник (``parent_id``) для группировки номенклатуры в
каталоге покупателя. Категории создаются в админке/справочниках.

См. также: :mod:`app.models.catalog.nomenklatura`.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class Category(Base, IdMixin, TimestampMixin):
    """Категория товаров (иерархическая)."""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    # Порядок отображения внутри родителя.
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    parent: Mapped["Category | None"] = relationship(remote_side="Category.id")
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", order_by="Category.sort, Category.id"
    )
