"""Справочник номенклатуры и типы цен.

Иерархический справочник (``parent_id``) с произвольными свойствами (цвет, размер)
через JSONB-колонку ``properties``.

См. также: :mod:`app.models.enums`, :mod:`app.models.catalog.valyuty`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin
from app.models.enums import NomenklaturaVid


class Nomenklatura(Base, IdMixin, TimestampMixin):
    """Номенклатура (товар/материал/продукция/тара/услуга)."""

    __tablename__ = "nomenklatura"

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("nomenklatura.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(65), nullable=True)
    vid: Mapped[NomenklaturaVid] = mapped_column(
        String(20), default=NomenklaturaVid.TOVAR, nullable=False
    )
    artikul: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_unit_id: Mapped[int | None] = mapped_column(ForeignKey("edinitsy.id"), nullable=True)
    main_unit_id: Mapped[int | None] = mapped_column(ForeignKey("edinitsy.id"), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    is_weighted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(13), nullable=True)
    nds_rate_id: Mapped[int | None] = mapped_column(ForeignKey("stavki_nds.id"), nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Цены: закупочная (база для наценки) и свободная розничная (без видов цен).
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    retail_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    parent: Mapped["Nomenklatura | None"] = relationship(remote_side="Nomenklatura.id")
    base_unit: Mapped["Edinitsa | None"] = relationship(foreign_keys=[base_unit_id])  # noqa: F821
    main_unit: Mapped["Edinitsa | None"] = relationship(foreign_keys=[main_unit_id])  # noqa: F821
    nds_rate: Mapped["StavkaNDS | None"] = relationship()  # noqa: F821


class TipTsen(Base, IdMixin, TimestampMixin):
    """Тип цен (оптовая, розничная, мелкооптовая и т.д.)."""

    __tablename__ = "tipy_tsen"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("valyuty.id"), nullable=True)
    includes_nds: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    markup_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    currency: Mapped["Valyuta | None"] = relationship()  # noqa: F821


class TsenaNomenklatury(Base, IdMixin, TimestampMixin):
    """Цена номенклатуры по типу цен."""

    __tablename__ = "tseny_nomenklatury"

    nomenklatura_id: Mapped[int] = mapped_column(ForeignKey("nomenklatura.id"), nullable=False)
    tip_tsen_id: Mapped[int] = mapped_column(ForeignKey("tipy_tsen.id"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    nomenklatura: Mapped[Nomenklatura] = relationship()
    tip_tsen: Mapped[TipTsen] = relationship()
