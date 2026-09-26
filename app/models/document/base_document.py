"""Документы: общая модель (шапка + табличная часть).

Используется единая таблица :class:`Document` с дискриминатором
:attr:`Document.doc_type` и JSONB-колонкой ``extra`` для реквизитов, специфичных
для конкретного вида документа. Такой подход проще расширять, чем «таблица на
каждый документ» в 1С 7.7, сохраняя при этом строгую типизацию общих полей.

См. также: :mod:`app.models.enums`, :mod:`app.models.registry`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin
from app.models.enums import DocumentStatus, DocType


class Document(Base, IdMixin, TimestampMixin):
    """Шапка документа."""

    __tablename__ = "documents"

    doc_type: Mapped[DocType] = mapped_column(String(30), nullable=False, index=True)
    # Подвид (наличный/кредит/на реализацию) для накладных.
    subtype: Mapped[str | None] = mapped_column(String(20), nullable=True)

    number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        String(20), default=DocumentStatus.DRAFT, nullable=False, index=True
    )

    firma_id: Mapped[int | None] = mapped_column(ForeignKey("firmy.id"), nullable=True)
    kontragent_id: Mapped[int | None] = mapped_column(ForeignKey("kontragenty.id"), nullable=True)
    dogovor_id: Mapped[int | None] = mapped_column(ForeignKey("dogovory.id"), nullable=True)
    sklad_id: Mapped[int | None] = mapped_column(ForeignKey("sklady.id"), nullable=True)
    sklad_to_id: Mapped[int | None] = mapped_column(ForeignKey("sklady.id"), nullable=True)
    kassa_id: Mapped[int | None] = mapped_column(ForeignKey("kassy.id"), nullable=True)
    valyuta_id: Mapped[int | None] = mapped_column(ForeignKey("valyuty.id"), nullable=True)

    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    nds_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Реквизиты, специфичные для вида документа (срок кредита, основание и т.п.).
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    firma: Mapped["Firma | None"] = relationship()  # noqa: F821
    kontragent: Mapped["Kontragent | None"] = relationship()  # noqa: F821
    dogovor: Mapped["Dogovor | None"] = relationship()  # noqa: F821
    sklad: Mapped["Sklad | None"] = relationship(foreign_keys=[sklad_id])  # noqa: F821
    sklad_to: Mapped["Sklad | None"] = relationship(foreign_keys=[sklad_to_id])  # noqa: F821
    kassa: Mapped["Kassa | None"] = relationship()  # noqa: F821
    valyuta: Mapped["Valyuta | None"] = relationship()  # noqa: F821
    created_by: Mapped["User | None"] = relationship()  # noqa: F821

    items: Mapped[list["DocumentItem"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentItem.id",
    )
    movements: Mapped[list["StockMovement"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentItem(Base, IdMixin):
    """Строка табличной части документа."""

    __tablename__ = "document_items"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    nomenklatura_id: Mapped[int] = mapped_column(ForeignKey("nomenklatura.id"), nullable=False)
    sklad_id: Mapped[int | None] = mapped_column(ForeignKey("sklady.id"), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    nds_rate_id: Mapped[int | None] = mapped_column(ForeignKey("stavki_nds.id"), nullable=True)
    nds_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)

    document: Mapped[Document] = relationship(back_populates="items")
    nomenklatura: Mapped["Nomenklatura"] = relationship()  # noqa: F821
    nds_rate: Mapped["StavkaNDS | None"] = relationship()  # noqa: F821
    sklad: Mapped["Sklad | None"] = relationship()  # noqa: F821
