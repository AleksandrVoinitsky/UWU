"""Справочники: валюты, ставки НДС, единицы измерения.

См. также: :mod:`app.models.base`, :mod:`app.models.enums`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class Valyuta(Base, IdMixin, TimestampMixin):
    """Валюта (код, наименование). Курс — периодический, см. :class:`CurrencyRate`."""

    __tablename__ = "valyuty"

    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)

    rates: Mapped[list["CurrencyRate"]] = relationship(
        back_populates="currency", cascade="all, delete-orphan"
    )


class CurrencyRate(Base, IdMixin):
    """Периодическое значение курса валюты на дату."""

    __tablename__ = "currency_rates"
    __table_args__ = (UniqueConstraint("currency_id", "on_date", name="uq_rate_currency_date"),)

    currency_id: Mapped[int] = mapped_column(ForeignKey("valyuty.id"), nullable=False)
    on_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    multiplicity: Mapped[int] = mapped_column(Numeric(10, 0), default=1, nullable=False)

    currency: Mapped[Valyuta] = relationship(back_populates="rates")


class StavkaNDS(Base, IdMixin, TimestampMixin):
    """Ставка НДС (20%, 10%, 0%, без НДС)."""

    __tablename__ = "stavki_nds"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Edinitsa(Base, IdMixin, TimestampMixin):
    """Единица измерения (наименование, сокращение, коэффициент)."""

    __tablename__ = "edinitsy"

    name: Mapped[str] = mapped_column(String(10), nullable=False)
    short_name: Mapped[str] = mapped_column(String(5), nullable=False)
    coefficient: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=1, nullable=False)
