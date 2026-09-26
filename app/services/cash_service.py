"""Кассовые смены: открытие/закрытие и X/Z-отчёт.

См. также: :mod:`app.models.registry.CashShift`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.registry import CashShift, MoneyMovement


async def get_open_shift(session: AsyncSession, kassa_id: int | None = None) -> CashShift | None:
    """Открытая смена (по кассе или любая)."""
    stmt = select(CashShift).where(CashShift.status == "open")
    if kassa_id is not None:
        stmt = stmt.where(CashShift.kassa_id == kassa_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def open_shift(
    session: AsyncSession, *, kassa_id: int | None, opening_amount: Decimal, user_id: int | None
) -> CashShift:
    # Запрещаем вторую открытую смену той же кассы.
    existing = await get_open_shift(session, kassa_id)
    if existing is not None:
        return existing
    shift = CashShift(
        kassa_id=kassa_id,
        status="open",
        opening_amount=opening_amount,
        opened_by_id=user_id,
    )
    session.add(shift)
    await session.commit()
    await session.refresh(shift)
    return shift


async def close_shift(session: AsyncSession, shift: CashShift, closing_amount: Decimal) -> CashShift:
    shift.status = "closed"
    shift.closed_at = datetime.now(timezone.utc)
    shift.closing_amount = closing_amount
    await session.commit()
    await session.refresh(shift)
    return shift


def _shift_window(shift: CashShift) -> list:
    """Условия окна смены: по кассе и датам (открытия → закрытия).

    Раньше движения считались только по дате и знаку — без фильтра по кассе и
    верхней границы, поэтому при нескольких кассах или операциях вне окна
    смены X/Z-отчёт был неверен.
    """
    conds = [MoneyMovement.date >= shift.opened_at.date()]
    if shift.kassa_id is not None:
        conds.append(MoneyMovement.kassa_id == shift.kassa_id)
    if shift.closed_at is not None:
        conds.append(MoneyMovement.date <= shift.closed_at.date())
    return conds


async def shift_revenue(session: AsyncSession, shift: CashShift) -> Decimal:
    """Выручка за смену (положительные движения денег в окне смены)."""
    stmt = select(func.coalesce(func.sum(MoneyMovement.amount), 0)).where(
        *_shift_window(shift), MoneyMovement.amount > 0
    )
    return (await session.execute(stmt)).scalar() or Decimal("0")


async def shift_expenses(session: AsyncSession, shift: CashShift) -> Decimal:
    """Расход за смену (отрицательные движения денег в окне смены)."""
    stmt = select(func.coalesce(func.sum(MoneyMovement.amount), 0)).where(
        *_shift_window(shift), MoneyMovement.amount < 0
    )
    return -(await session.execute(stmt)).scalar() or Decimal("0")
