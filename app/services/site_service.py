"""Сервис управления сайтом/MiniApp: настройки, акции, цены со скидкой.

Управляет тем, что видит покупатель (логотип, баннер, оформление карточек) и
акциями (скидками). Вызывается админкой и каталогом покупателя.

См. также: :mod:`app.models.site`, :mod:`app.web.site_admin`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site import DEFAULT_SITE_SETTINGS, Promotion, SiteSetting


# --- Настройки сайта ----------------------------------------------------------


async def get_settings(session: AsyncSession) -> dict:
    """Настройки сайта как словарь (с дефолтами)."""
    result = await session.execute(select(SiteSetting))
    stored = {s.key: s.value for s in result.scalars()}
    merged = dict(DEFAULT_SITE_SETTINGS)
    merged.update(stored)
    return merged


async def set_settings(session: AsyncSession, values: dict) -> None:
    """Сохраняет настройки сайта (по одной, сохраняя тип значения)."""
    for key, value in values.items():
        stmt = select(SiteSetting).where(SiteSetting.key == key)
        setting = (await session.execute(stmt)).scalar_one_or_none()
        if setting is None:
            setting = SiteSetting(key=key, value=value)
            session.add(setting)
        else:
            setting.value = value
    await session.commit()


# --- Акции --------------------------------------------------------------------


async def list_promotions(session: AsyncSession) -> list[Promotion]:
    result = await session.execute(select(Promotion).order_by(Promotion.id.desc()))
    return list(result.scalars())


async def get_promotion(session: AsyncSession, promotion_id: int) -> Promotion | None:
    return await session.get(Promotion, promotion_id)


async def create_promotion(
    session: AsyncSession,
    *,
    name: str,
    discount_type: str,
    value: Decimal,
    description: str | None = None,
    nomenklatura_id: int | None = None,
    category_id: int | None = None,
    enabled: bool = True,
    starts_at: date | None = None,
    ends_at: date | None = None,
) -> Promotion:
    promo = Promotion(
        name=name,
        description=description,
        discount_type=discount_type,
        value=value,
        nomenklatura_id=nomenklatura_id,
        category_id=category_id,
        enabled=enabled,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


async def update_promotion(
    session: AsyncSession,
    promo: Promotion,
    *,
    name: str | None = None,
    description: str | None = None,
    discount_type: str | None = None,
    value: Decimal | None = None,
    nomenklatura_id: int | None = None,
    category_id: int | None = None,
    enabled: bool | None = None,
    starts_at: date | None = None,
    ends_at: date | None = None,
) -> Promotion:
    if name is not None:
        promo.name = name
    if description is not None:
        promo.description = description
    if discount_type is not None:
        promo.discount_type = discount_type
    if value is not None:
        promo.value = value
    if nomenklatura_id is not None:
        promo.nomenklatura_id = nomenklatura_id
    if category_id is not None:
        promo.category_id = category_id
    if enabled is not None:
        promo.enabled = enabled
    if starts_at is not None:
        promo.starts_at = starts_at
    if ends_at is not None:
        promo.ends_at = ends_at
    await session.commit()
    await session.refresh(promo)
    return promo


async def delete_promotion(session: AsyncSession, promo: Promotion) -> None:
    await session.delete(promo)
    await session.commit()


def _active_on(promo: Promotion, on: date) -> bool:
    if not promo.enabled:
        return False
    if promo.starts_at is not None and on < promo.starts_at:
        return False
    if promo.ends_at is not None and on > promo.ends_at:
        return False
    return True


def find_promotion(
    promos: list[Promotion],
    nomenklatura_id: int,
    category_id: int | None,
    on: date | None = None,
) -> Promotion | None:
    """Чистая функция: активная акция для товара по списку промо (без обращений к БД).

    Приоритет: товар → категория → глобальная (без привязки).
    """
    on = on or date.today()
    by_product = [p for p in promos if p.nomenklatura_id == nomenklatura_id and _active_on(p, on)]
    if by_product:
        return by_product[0]
    if category_id is not None:
        by_category = [p for p in promos if p.category_id == category_id and _active_on(p, on)]
        if by_category:
            return by_category[0]
    global_ = [
        p for p in promos
        if p.nomenklatura_id is None and p.category_id is None and _active_on(p, on)
    ]
    return global_[0] if global_ else None


async def promotion_for(
    session: AsyncSession,
    nomenklatura_id: int,
    category_id: int | None,
    on: date | None = None,
) -> Promotion | None:
    """Активная акция для товара (обёртка над :func:`find_promotion`)."""
    promos = await list_promotions(session)
    return find_promotion(promos, nomenklatura_id, category_id, on)


def apply_discount(base_price: Decimal, promo: Promotion) -> Decimal:
    """Цена после скидки (не ниже нуля)."""
    base = base_price or Decimal("0")
    if promo.discount_type == "fixed":
        result = base - promo.value
    else:  # percent
        result = base * (Decimal("1") - promo.value / Decimal("100"))
    if result < 0:
        result = Decimal("0")
    return result.quantize(Decimal("0.01"))
