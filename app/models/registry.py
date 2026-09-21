"""Регистры: движения и остатки (товары, партии, деньги, взаиморасчёты).

Регистры — основа учёта. Проведение документа порождает движения
(:class:`StockMovement`, :class:`MoneyMovement`, :class:`SettlementMovement`), а
остатки выводятся агрегацией. Партионный учёт ведётся в :class:`StockBatch`.

См. также: :mod:`app.models.document.base_document`,
:mod:`app.services.stock_service`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class StockBatch(Base, IdMixin):
    """Партия товара (остаток по номенклатуре на складе с себестоимостью)."""

    __tablename__ = "stock_batches"

    nomenklatura_id: Mapped[int] = mapped_column(
        ForeignKey("nomenklatura.id"), nullable=False, index=True
    )
    sklad_id: Mapped[int] = mapped_column(ForeignKey("sklady.id"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    # Раздельный учёт: own (собственные), received (принятые на реализацию), transferred (переданные на реализацию).
    ownership: Mapped[str] = mapped_column(String(20), default="own", nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    nomenklatura: Mapped["Nomenklatura"] = relationship()  # noqa: F821
    sklad: Mapped["Sklad"] = relationship()  # noqa: F821


class StockMovement(Base, IdMixin):
    """Движение товара (одна запись на строку проведённого документа)."""

    __tablename__ = "stock_movements"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nomenklatura_id: Mapped[int] = mapped_column(ForeignKey("nomenklatura.id"), nullable=False, index=True)
    sklad_id: Mapped[int] = mapped_column(ForeignKey("sklady.id"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)  # + приход / - расход
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)   # + приход / - расход
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("stock_batches.id"), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="movements")  # noqa: F821
    nomenklatura: Mapped["Nomenklatura"] = relationship()  # noqa: F821
    sklad: Mapped["Sklad"] = relationship()  # noqa: F821


class MoneyMovement(Base, IdMixin):
    """Движение денежных средств по кассе/счёту."""

    __tablename__ = "money_movements"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kassa_id: Mapped[int | None] = mapped_column(ForeignKey("kassy.id"), nullable=True)
    kontragent_id: Mapped[int | None] = mapped_column(ForeignKey("kontragenty.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # + приход / - расход

    document: Mapped["Document"] = relationship()  # noqa: F821
    kassa: Mapped["Kassa | None"] = relationship()  # noqa: F821
    kontragent: Mapped["Kontragent | None"] = relationship()  # noqa: F821


class SettlementMovement(Base, IdMixin):
    """Движение по взаиморасчётам с контрагентами."""

    __tablename__ = "settlement_movements"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kontragent_id: Mapped[int] = mapped_column(ForeignKey("kontragenty.id"), nullable=False, index=True)
    dogovor_id: Mapped[int | None] = mapped_column(ForeignKey("dogovory.id"), nullable=True)
    # Основание: документ-накладная, которую погашает данное движение (для оплат).
    base_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # + долг нам / - долг мы

    document: Mapped["Document"] = relationship(foreign_keys=[document_id])  # noqa: F821
    base_document: Mapped["Document | None"] = relationship(foreign_keys=[base_document_id])  # noqa: F821
    kontragent: Mapped["Kontragent"] = relationship()  # noqa: F821
    dogovor: Mapped["Dogovor | None"] = relationship()  # noqa: F821


class Reservation(Base, IdMixin, TimestampMixin):
    """Резерв товара под заявку/клиента (уменьшает доступный остаток)."""

    __tablename__ = "reservations"

    nomenklatura_id: Mapped[int] = mapped_column(ForeignKey("nomenklatura.id"), nullable=False, index=True)
    sklad_id: Mapped[int] = mapped_column(ForeignKey("sklady.id"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    zakaz_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)

    nomenklatura: Mapped["Nomenklatura"] = relationship()  # noqa: F821
    sklad: Mapped["Sklad"] = relationship()  # noqa: F821


class AccountingEntry(Base, IdMixin):
    """Бухгалтерская проводка (автоматически формируется при проведении)."""

    __tablename__ = "accounting_entries"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account_debit: Mapped[str] = mapped_column(String(20), nullable=False)
    account_credit: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    nomenklatura_id: Mapped[int | None] = mapped_column(ForeignKey("nomenklatura.id"), nullable=True)
    kontragent_id: Mapped[int | None] = mapped_column(ForeignKey("kontragenty.id"), nullable=True)

    document: Mapped["Document"] = relationship()  # noqa: F821
