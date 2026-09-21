"""Схемы документов.

См. также: :mod:`app.models.document.base_document`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentItemCreate(BaseModel):
    """Строка табличной части при создании документа."""

    nomenklatura_id: int
    sklad_id: int | None = None
    quantity: Decimal
    price: Decimal
    nds_rate_id: int | None = None


class DocumentCreate(BaseModel):
    """Создание документа."""

    doc_type: str
    subtype: str | None = None
    date: date
    number: str | None = None  # авто, если не задан
    firma_id: int | None = None
    kontragent_id: int | None = None
    dogovor_id: int | None = None
    sklad_id: int | None = None
    sklad_to_id: int | None = None
    kassa_id: int | None = None
    valyuta_id: int | None = None
    comment: str | None = None
    total: Decimal | None = None  # для денежных документов без табличной части
    extra: dict[str, Any] = Field(default_factory=dict)
    items: list[DocumentItemCreate] = Field(default_factory=list)


class DocumentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nomenklatura_id: int
    sklad_id: int | None
    quantity: Decimal
    price: Decimal
    amount: Decimal
    nds_rate_id: int | None
    nds_amount: Decimal


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: str
    subtype: str | None
    number: str
    date: date
    status: str
    firma_id: int | None
    kontragent_id: int | None
    dogovor_id: int | None
    sklad_id: int | None
    sklad_to_id: int | None
    kassa_id: int | None
    valyuta_id: int | None
    total: Decimal
    nds_total: Decimal
    comment: str | None
    posted_at: datetime | None
    extra: dict[str, Any]
    items: list[DocumentItemOut] = Field(default_factory=list)


class DocumentListOut(BaseModel):
    """Краткая карточка документа для журналов."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: str
    number: str
    date: date
    status: str
    total: Decimal
    kontragent_id: int | None
