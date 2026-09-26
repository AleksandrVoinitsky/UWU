"""API отчётов.

Все эндпоинты требуют аутентификацию и право ``reports.read``.

См. также: :mod:`app.services.report_service`, :mod:`app.core.deps`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import require_permission
from app.models.users import User
from app.services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])

READ = Depends(require_permission("reports.read"))

MAX_RANGE_DAYS = 366


def _validate_period(start: date, end: date) -> None:
    """Проверка периода: start <= end и диапазон не более MAX_RANGE_DAYS."""
    if start > end:
        raise HTTPException(status_code=400, detail="start must be less than or equal to end")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"period must not exceed {MAX_RANGE_DAYS} days",
        )


@router.get("/stock/balances")
async def stock_balances(
    session: AsyncSession = Depends(get_session),
    _user: User = READ,
):
    return await report_service.stock_balances(session)


@router.get("/stock/movements")
async def stock_movements(
    start: date,
    end: date,
    nomenklatura_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = READ,
):
    _validate_period(start, end)
    return await report_service.stock_movements(session, start, end, nomenklatura_id)


@router.get("/sales")
async def sales(
    start: date,
    end: date,
    session: AsyncSession = Depends(get_session),
    _user: User = READ,
):
    _validate_period(start, end)
    return await report_service.sales_report(session, start, end)


@router.get("/settlements")
async def settlements(
    firma_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = READ,
):
    return await report_service.settlement_balances(session, firma_id)


@router.get("/money/balance")
async def money_balance(
    firma_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = READ,
):
    return {"balance": str(await report_service.money_balance(session, firma_id))}


@router.get("/money/movements")
async def money_movements(
    start: date,
    end: date,
    firma_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = READ,
):
    _validate_period(start, end)
    return await report_service.money_movements(session, start, end, firma_id)
