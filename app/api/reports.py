"""API отчётов.

См. также: :mod:`app.services.report_service`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/stock/balances")
async def stock_balances(session: AsyncSession = Depends(get_session)):
    return await report_service.stock_balances(session)


@router.get("/stock/movements")
async def stock_movements(
    start: date,
    end: date,
    nomenklatura_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await report_service.stock_movements(session, start, end, nomenklatura_id)


@router.get("/sales")
async def sales(start: date, end: date, session: AsyncSession = Depends(get_session)):
    return await report_service.sales_report(session, start, end)


@router.get("/settlements")
async def settlements(session: AsyncSession = Depends(get_session)):
    return await report_service.settlement_balances(session)


@router.get("/money/balance")
async def money_balance(session: AsyncSession = Depends(get_session)):
    return {"balance": str(await report_service.money_balance(session))}


@router.get("/money/movements")
async def money_movements(
    start: date, end: date, session: AsyncSession = Depends(get_session)
):
    return await report_service.money_movements(session, start, end)
