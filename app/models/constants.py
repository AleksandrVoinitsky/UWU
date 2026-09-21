"""Константы (глобальные настройки сервиса).

Хранятся как пары ключ-значение (JSONB). Значения по умолчанию описаны в
:data:`DEFAULT_CONSTANTS`.

См. также: :mod:`app.services.catalog_service`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin

# Значения констант по умолчанию (ключ -> значение).
DEFAULT_CONSTANTS: dict[str, Any] = {
    "currency_buh_id": None,        # Валюта бухгалтерского учёта
    "currency_upr_id": None,        # Валюта управленческого учёта
    "restock_control": "by_warehouse",  # by_firm | by_warehouse | none
    "retail_price_type_id": None,   # Розничный тип цен
    "weight_unit_id": None,         # Единица веса
    "show_artikul": False,          # Показывать артикул в формах
    "allow_future_dates": False,    # Разрешить будущие даты
    "cost_method": "fifo",          # Метод списания себестоимости
    "prefix_ib": "",                # Префикс информационной базы
    "enforce_min_price": False,     # Контроль минимальной цены (не ниже закупочной)
    # Шапка печатной формы накладной.
    "invoice_company_name": "",     # Название организации
    "invoice_company_inn": "",      # ИНН
    "invoice_company_address": "",  # Адрес
    "invoice_footer": "",           # Доп. текст в подвале
}


class Constant(Base, IdMixin, TimestampMixin):
    """Одна константа (ключ -> значение)."""

    __tablename__ = "constants"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
