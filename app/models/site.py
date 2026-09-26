"""Настройки клиентского сайта/MiniApp и акции.

Плоскость управления тем, что видит покупатель: логотип, рекламный баннер,
оформление карточек товаров и акции (скидки). Управляется из админки
(``/admin/site``); покупателю отдаётся через каталог.

См. также: :mod:`app.services.site_service`, :mod:`app.web.site_admin`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin

# Значения настроек сайта по умолчанию.
DEFAULT_SITE_SETTINGS: dict[str, Any] = {
    "logo_path": None,             # путь к логотипу (относительно /uploads)
    "banner_image_path": None,     # картинка баннера
    "banner_text": "",             # текст баннера
    "banner_link": "",             # ссылка баннера (опционально)
    "banner_enabled": False,       # показывать баннер
    "card_style": "grid",          # grid | compact | list
    "show_prices": True,           # показывать цену на карточке
    "show_description": True,      # показывать полное наименование
}

# Типы скидки акции.
DISCOUNT_TYPES = ("percent", "fixed")


class SiteSetting(Base, IdMixin, TimestampMixin):
    """Одна настройка сайта (ключ -> JSONB-значение)."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)


class Promotion(Base, IdMixin, TimestampMixin):
    """Акция: скидка на товар или категорию (для клиентского сайта)."""

    __tablename__ = "promotions"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # percent | fixed
    discount_type: Mapped[str] = mapped_column(String(20), default="percent", nullable=False)
    # Для percent — процент скидки (0–100); для fixed — сумма скидки.
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Цель акции: конкретный товар или вся категория (оба — null = на всё).
    nomenklatura_id: Mapped[int | None] = mapped_column(ForeignKey("nomenklatura.id"), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
