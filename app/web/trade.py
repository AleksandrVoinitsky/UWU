"""Веб-интерфейс торгового учёта (для операторов и бухгалтеров).

Главное меню: справочники, документы, журналы, отчёты.

См. также: :mod:`app.services.document_service`,
:mod:`app.services.report_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user_from_cookie
from app.core.i18n import translate
from app.models import catalog as cat
from app.models.document.base_document import Document
from app.models.enums import DocSubtype, DocType, DocumentStatus
from app.models.users import User
from app.services import catalog_service, document_service, report_service
from app.services.stock_service import InsufficientStockError
from app.templates import render

router = APIRouter(tags=["web-trade"])


def _lang(request: Request) -> str:
    return request.cookies.get("lang") or "ru"


def _page(request: Request, user: User, template: str, **ctx) -> HTMLResponse:
    return HTMLResponse(
        render(template, lang=_lang(request), t=translate, user=user, section="trade", **ctx)
    )


# --- Главное меню ---


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if user.is_admin:
        return RedirectResponse("/admin", status_code=303)
    money = await report_service.money_balance(session)
    return _page(request, user, "trade/dashboard.html", money=money)


# --- Справочники ---


async def _list_catalog(
    request: Request, user: User, session: AsyncSession, model, template: str, title_key: str
) -> HTMLResponse:
    items = await catalog_service.list_all(session, model)
    return _page(request, user, template, items=items)


@router.get("/catalog/nomenklatura", response_class=HTMLResponse)
async def catalog_nomenklatura(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    items = await catalog_service.list_all(session, cat.Nomenklatura)
    units = await catalog_service.list_all(session, cat.Edinitsa)
    nds = await catalog_service.list_all(session, cat.StavkaNDS)
    return _page(request, user, "trade/nomenklatura.html", items=items, units=units, nds=nds)


@router.post("/catalog/nomenklatura")
async def create_nomenklatura(
    name: str = Form(...),
    full_name: str = Form(""),
    vid: str = Form("tovar"),
    artikul: str = Form(""),
    base_unit_id: str = Form(""),
    nds_rate_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    code = await catalog_service.next_nomenklatura_code(session)
    await catalog_service.create_one(
        session,
        cat.Nomenklatura,
        code=code,
        name=name,
        full_name=full_name or None,
        vid=vid,
        artikul=artikul or None,
        base_unit_id=int(base_unit_id) if base_unit_id else None,
        nds_rate_id=int(nds_rate_id) if nds_rate_id else None,
    )
    return RedirectResponse("/catalog/nomenklatura", status_code=303)


@router.get("/catalog/kontragenty", response_class=HTMLResponse)
async def catalog_kontragenty(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    items = await catalog_service.list_all(session, cat.Kontragent)
    return _page(request, user, "trade/kontragenty.html", items=items)


@router.post("/catalog/kontragenty")
async def create_kontragent(
    name: str = Form(...),
    full_name: str = Form(""),
    inn: str = Form(""),
    phones: str = Form(""),
    vid: str = Form("yur"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    code = await catalog_service.next_kontragent_code(session)
    await catalog_service.create_one(
        session,
        cat.Kontragent,
        code=code,
        name=name,
        full_name=full_name or None,
        inn=inn or None,
        phones=phones or None,
        vid=vid,
    )
    return RedirectResponse("/catalog/kontragenty", status_code=303)


@router.get("/catalog/sklady", response_class=HTMLResponse)
async def catalog_sklady(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    items = await catalog_service.list_all(session, cat.Sklad)
    return _page(request, user, "trade/sklady.html", items=items)


@router.post("/catalog/sklady")
async def create_sklad(
    code: str = Form(...),
    name: str = Form(...),
    tip: str = Form("optovy"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.Sklad, code=code, name=name, tip=tip)
    return RedirectResponse("/catalog/sklady", status_code=303)


# --- Документы (журнал) ---


@router.get("/documents", response_class=HTMLResponse)
async def documents_journal(
    request: Request,
    doc_type: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    stmt = select(Document).order_by(Document.date.desc(), Document.id.desc())
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    result = await session.execute(stmt)
    documents = list(result.scalars())
    return _page(
        request,
        user,
        "trade/documents.html",
        documents=documents,
        doc_type=doc_type,
        DocType=DocType,
    )


@router.get("/documents/new", response_class=HTMLResponse)
async def document_new_form(
    request: Request,
    doc_type: str = "rashod",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    nomenklatura = await catalog_service.list_all(session, cat.Nomenklatura)
    sklady = await catalog_service.list_all(session, cat.Sklad)
    kontragenty = await catalog_service.list_all(session, cat.Kontragent)
    kassy = await catalog_service.list_all(session, cat.Kassa)
    firmy = await catalog_service.list_all(session, cat.Firma)
    return _page(
        request,
        user,
        "trade/document_form.html",
        doc_type=doc_type,
        DocType=DocType,
        nomenklatura=nomenklatura,
        sklady=sklady,
        kontragenty=kontragenty,
        kassy=kassy,
        firmy=firmy,
        today=date.today().isoformat(),
    )


@router.post("/documents/new")
async def document_create_submit(
    request: Request,
    doc_type: str = Form(...),
    subtype: str = Form(""),
    doc_date: str = Form(...),
    sklad_id: str = Form(""),
    sklad_to_id: str = Form(""),
    kontragent_id: str = Form(""),
    kassa_id: str = Form(""),
    firma_id: str = Form(""),
    comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    form = await request.form()
    items = _parse_items(form)
    amount = form.get("amount")
    total = Decimal(amount) if amount else None
    try:
        document = await document_service.create_document(
            session,
            doc_type=DocType(doc_type),
            subtype=DocSubtype(subtype) if subtype else None,
            doc_date=date.fromisoformat(doc_date),
            sklad_id=int(sklad_id) if sklad_id else None,
            sklad_to_id=int(sklad_to_id) if sklad_to_id else None,
            kontragent_id=int(kontragent_id) if kontragent_id else None,
            kassa_id=int(kassa_id) if kassa_id else None,
            firma_id=int(firma_id) if firma_id else None,
            comment=comment or None,
            total=total,
            items=items,
            created_by_id=user.id,
        )
        await document_service.post_document(session, document)
    except (InsufficientStockError, document_service.DocumentError) as exc:
        return _page(request, user, "trade/error.html", error=str(exc))
    return RedirectResponse("/documents", status_code=303)


def _parse_items(form) -> list[dict]:
    """Разбирает строки табличной части из формы (nomenklatura_id[], qty[], price[])."""
    nomen_ids = form.getlist("item_nomenklatura_id")
    qtys = form.getlist("item_quantity")
    prices = form.getlist("item_price")
    items = []
    for nomen_id, qty, price in zip(nomen_ids, qtys, prices):
        if not nomen_id or not qty:
            continue
        items.append(
            {
                "nomenklatura_id": int(nomen_id),
                "quantity": Decimal(qty),
                "price": Decimal(price),
            }
        )
    return items


@router.post("/documents/{document_id}/post")
async def document_post(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    document = await document_service.get_document(session, document_id)
    if document:
        try:
            await document_service.post_document(session, document)
        except (InsufficientStockError, document_service.DocumentError):
            pass
    return RedirectResponse("/documents", status_code=303)


@router.post("/documents/{document_id}/unpost")
async def document_unpost(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    document = await document_service.get_document(session, document_id)
    if document:
        await document_service.unpost_document(session, document)
    return RedirectResponse("/documents", status_code=303)


@router.post("/documents/{document_id}/delete")
async def document_delete(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    document = await document_service.get_document(session, document_id)
    if document:
        await document_service.mark_for_deletion(session, document)
    return RedirectResponse("/documents", status_code=303)


# --- Отчёты ---


@router.get("/reports", response_class=HTMLResponse)
async def reports_index(
    request: Request,
    user: User = Depends(get_current_user_from_cookie),
):
    return _page(request, user, "trade/reports.html")


@router.get("/reports/stock", response_class=HTMLResponse)
async def report_stock(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    balances = await report_service.stock_balances(session)
    return _page(request, user, "trade/report_stock.html", balances=balances)


@router.get("/reports/settlements", response_class=HTMLResponse)
async def report_settlements(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    rows = await report_service.settlement_balances(session)
    return _page(request, user, "trade/report_settlements.html", rows=rows)


@router.get("/reports/money", response_class=HTMLResponse)
async def report_money(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    balance = await report_service.money_balance(session)
    return _page(request, user, "trade/report_money.html", balance=balance)
