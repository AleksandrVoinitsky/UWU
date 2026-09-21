"""Веб-интерфейс торгового учёта (для операторов и бухгалтеров).

Главное меню: справочники, документы, журналы, отчёты.

См. также: :mod:`app.services.document_service`,
:mod:`app.services.report_service`.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.deps import get_current_user_from_cookie
from app.core.i18n import translate
from app.models import catalog as cat
from app.models.document.base_document import Document
from app.models.enums import DocSubtype, DocType, DocumentStatus
from app.models.users import User
from app.services import catalog_service, document_service, price_service, report_service, stock_service
from app.services.stock_service import InsufficientStockError
from app.templates import render

router = APIRouter(tags=["web-trade"])

# Названия документов для отображения.
DOC_LABELS = {
    "prihod": "Приходная накладная",
    "rashod": "Расходная накладная",
    "peremeshenie": "Перемещение",
    "spisanie": "Списание",
    "oprihodovanie": "Оприходование",
    "vvod_ostatkov": "Ввод остатков ТМЦ",
    "pko": "Приходный кассовый ордер",
    "rko": "Расходный кассовый ордер",
    "platezhnoe_poruchenie": "Платёжное поручение",
    "vvod_ostatkov_deneg": "Ввод остатков денег",
    "zakaz": "Заявка покупателя",
    "vozvrat": "Возврат товара",
}

ZAKAZ_STATES = {
    "new": "Новая",
    "in_work": "В работе",
    "done": "Выполнена",
    "cancelled": "Отменена",
}

# Виды документов, у которых есть табличная часть.
_ITEM_DOCS = {"prihod", "rashod", "peremeshenie", "spisanie", "oprihodovanie", "vvod_ostatkov", "vozvrat"}
# Документы прихода (для подсказки в форме).
_MONEY_DOCS = {"pko", "rko", "platezhnoe_poruchenie", "vvod_ostatkov_deneg"}


def _lang(request: Request) -> str:
    return request.cookies.get("lang") or "ru"


def _page(request: Request, user: User, template: str, **ctx) -> HTMLResponse:
    return HTMLResponse(
        render(
            template,
            lang=_lang(request),
            t=translate,
            user=user,
            section="trade",
            DocType=DocType,
            DOC_LABELS=DOC_LABELS,
            **ctx,
        )
    )


def _month_range() -> tuple[str, str]:
    """Диапазон текущего месяца (для отчётов по умолчанию)."""
    today = date.today()
    start = today.replace(day=1)
    return start.isoformat(), today.isoformat()


# --- Главная ---


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if user.is_admin:
        return RedirectResponse("/admin", status_code=303)
    money = await report_service.money_balance(session)
    balances = await report_service.stock_balances(session)
    nomen_count = len(await catalog_service.list_all(session, cat.Nomenklatura))
    kg_count = len(await catalog_service.list_all(session, cat.Kontragent))
    stock_items = len(balances)
    total_stock_value = sum((b["cost"] for b in balances), Decimal("0"))
    return _page(
        request,
        user,
        "trade/dashboard.html",
        money=money,
        stock_items=stock_items,
        total_stock_value=total_stock_value,
        nomen_count=nomen_count,
        kg_count=kg_count,
    )


# --- Справочники (универсальные) ---


async def _catalog_page(request, user, session, model, template, title, **extra):
    items = await catalog_service.list_all(session, model)
    return _page(request, user, template, items=items, title=title, **extra)


@router.get("/catalog/nomenklatura", response_class=HTMLResponse)
async def catalog_nomenklatura(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    result = await session.execute(
        select(cat.Nomenklatura)
        .options(
            selectinload(cat.Nomenklatura.base_unit),
            selectinload(cat.Nomenklatura.nds_rate),
            selectinload(cat.Nomenklatura.tip_tsen),
        )
        .order_by(cat.Nomenklatura.id)
    )
    items = list(result.scalars())
    units = await catalog_service.list_all(session, cat.Edinitsa)
    nds = await catalog_service.list_all(session, cat.StavkaNDS)
    tipy = await catalog_service.list_all(session, cat.TipTsen)
    tipy_map = {t.id: t for t in tipy}

    # Итоговая цена для таблицы.
    eff_prices = {
        n.id: price_service.effective_price(n, tipy_map) for n in items
    }

    return _page(
        request, user, "trade/nomenklatura.html",
        items=items, units=units, nds=nds, tipy=tipy, eff_prices=eff_prices,
    )


@router.post("/catalog/nomenklatura")
async def create_nomenklatura(
    name: str = Form(...), full_name: str = Form(""), vid: str = Form("tovar"),
    artikul: str = Form(""), base_unit_id: str = Form(""), nds_rate_id: str = Form(""),
    purchase_price: str = Form(""), retail_price: str = Form(""),
    price_mode: str = Form("free"), tip_tsen_id: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    code = await catalog_service.next_nomenklatura_code(session)
    await catalog_service.create_one(
        session, cat.Nomenklatura, code=code, name=name, full_name=full_name or None,
        vid=vid, artikul=artikul or None,
        base_unit_id=int(base_unit_id) if base_unit_id else None,
        nds_rate_id=int(nds_rate_id) if nds_rate_id else None,
        purchase_price=_or_decimal(purchase_price),
        retail_price=_or_decimal(retail_price),
        price_mode=price_mode if price_mode in ("free", "by_type") else "free",
        tip_tsen_id=int(tip_tsen_id) if (price_mode == "by_type" and tip_tsen_id) else None,
    )
    return RedirectResponse("/catalog/nomenklatura", status_code=303)


@router.get("/catalog/kontragenty", response_class=HTMLResponse)
async def catalog_kontragenty(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    items = await catalog_service.list_all(session, cat.Kontragent)
    return _page(request, user, "trade/kontragenty.html", items=items)


@router.post("/catalog/kontragenty")
async def create_kontragent(
    name: str = Form(...), full_name: str = Form(""), inn: str = Form(""),
    phones: str = Form(""), vid: str = Form("yur"),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    code = await catalog_service.next_kontragent_code(session)
    await catalog_service.create_one(
        session, cat.Kontragent, code=code, name=name, full_name=full_name or None,
        inn=inn or None, phones=phones or None, vid=vid,
    )
    return RedirectResponse("/catalog/kontragenty", status_code=303)


@router.get("/catalog/sklady", response_class=HTMLResponse)
async def catalog_sklady(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    return await _catalog_page(request, user, session, cat.Sklad, "trade/sklady.html", "Склады")


@router.post("/catalog/sklady")
async def create_sklad(
    code: str = Form(...), name: str = Form(...), tip: str = Form("optovy"),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.Sklad, code=code, name=name, tip=tip)
    return RedirectResponse("/catalog/sklady", status_code=303)


@router.get("/catalog/firmy", response_class=HTMLResponse)
async def catalog_firmy(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    return await _catalog_page(request, user, session, cat.Firma, "trade/firmy.html", "Фирмы")


@router.post("/catalog/firmy")
async def create_firma(
    name: str = Form(...), full_name: str = Form(""), inn: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(
        session, cat.Firma, name=name, full_name=full_name or None, inn=inn or None
    )
    return RedirectResponse("/catalog/firmy", status_code=303)


@router.get("/catalog/kassy", response_class=HTMLResponse)
async def catalog_kassy(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    items = await catalog_service.list_all(session, cat.Kassa)
    return _page(request, user, "trade/kassy.html", items=items)


@router.post("/catalog/kassy")
async def create_kassa(
    name: str = Form(...), session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.Kassa, name=name)
    return RedirectResponse("/catalog/kassy", status_code=303)


@router.get("/catalog/valyuty", response_class=HTMLResponse)
async def catalog_valyuty(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    items = await catalog_service.list_all(session, cat.Valyuta)
    rates = {}
    for v in items:
        r = await catalog_service.get_latest_rate(session, v.id)
        rates[v.id] = r
    return _page(request, user, "trade/valyuty.html", items=items, rates=rates)


@router.post("/catalog/valyuty")
async def create_valyuta(
    code: str = Form(...), name: str = Form(...),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.Valyuta, code=code, name=name)
    return RedirectResponse("/catalog/valyuty", status_code=303)


@router.get("/catalog/edinitsy", response_class=HTMLResponse)
async def catalog_edinitsy(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    return await _catalog_page(request, user, session, cat.Edinitsa, "trade/edinitsy.html", "Единицы измерения")


@router.post("/catalog/edinitsy")
async def create_edinitsa(
    name: str = Form(...), short_name: str = Form(...),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.Edinitsa, name=name, short_name=short_name)
    return RedirectResponse("/catalog/edinitsy", status_code=303)


@router.get("/catalog/stavki_nds", response_class=HTMLResponse)
async def catalog_stavki_nds(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    return await _catalog_page(request, user, session, cat.StavkaNDS, "trade/stavki_nds.html", "Ставки НДС")


@router.post("/catalog/stavki_nds")
async def create_stavka_nds(
    name: str = Form(...), rate: str = Form(...),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.StavkaNDS, name=name, rate=Decimal(rate))
    return RedirectResponse("/catalog/stavki_nds", status_code=303)


@router.get("/catalog/tipy_tsen", response_class=HTMLResponse)
async def catalog_tipy_tsen(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    return await _catalog_page(request, user, session, cat.TipTsen, "trade/tipy_tsen.html", "Типы цен")


@router.post("/catalog/tipy_tsen")
async def create_tip_tsen(
    name: str = Form(...), markup_percent: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(
        session, cat.TipTsen, name=name, markup_percent=_or_decimal(markup_percent)
    )
    return RedirectResponse("/catalog/tipy_tsen", status_code=303)


# --- Редактирование справочников (по клику на строку) ---


def _or_none(value: str) -> str | None:
    return value.strip() if value else None


def _or_decimal(value: str) -> Decimal | None:
    value = value.strip()
    return Decimal(value) if value else None


@router.post("/catalog/nomenklatura/{item_id}/update")
async def update_nomenklatura(
    item_id: int, name: str = Form(...), full_name: str = Form(""), vid: str = Form("tovar"),
    artikul: str = Form(""), purchase_price: str = Form(""), retail_price: str = Form(""),
    price_mode: str = Form("free"), tip_tsen_id: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Nomenklatura, item_id)
    if obj:
        obj.name = name
        obj.full_name = _or_none(full_name)
        obj.vid = vid
        obj.artikul = _or_none(artikul)
        # Цены задаём явно (пустое значение очищает цену).
        obj.purchase_price = _or_decimal(purchase_price)
        obj.retail_price = _or_decimal(retail_price)
        obj.price_mode = price_mode if price_mode in ("free", "by_type") else "free"
        obj.tip_tsen_id = int(tip_tsen_id) if (price_mode == "by_type" and tip_tsen_id) else None
        await session.commit()
    return RedirectResponse("/catalog/nomenklatura", status_code=303)


@router.post("/catalog/kontragenty/{item_id}/update")
async def update_kontragent(
    item_id: int, name: str = Form(...), full_name: str = Form(""), inn: str = Form(""),
    phones: str = Form(""), vid: str = Form("yur"),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Kontragent, item_id)
    if obj:
        await catalog_service.update_one(
            session, obj, name=name, full_name=_or_none(full_name), inn=_or_none(inn),
            phones=_or_none(phones), vid=vid,
        )
    return RedirectResponse("/catalog/kontragenty", status_code=303)


@router.post("/catalog/sklady/{item_id}/update")
async def update_sklad(
    item_id: int, code: str = Form(...), name: str = Form(...), tip: str = Form("optovy"),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Sklad, item_id)
    if obj:
        await catalog_service.update_one(session, obj, code=code, name=name, tip=tip)
    return RedirectResponse("/catalog/sklady", status_code=303)


@router.post("/catalog/firmy/{item_id}/update")
async def update_firma(
    item_id: int, name: str = Form(...), full_name: str = Form(""), inn: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Firma, item_id)
    if obj:
        await catalog_service.update_one(session, obj, name=name, full_name=_or_none(full_name), inn=_or_none(inn))
    return RedirectResponse("/catalog/firmy", status_code=303)


@router.post("/catalog/kassy/{item_id}/update")
async def update_kassa(
    item_id: int, name: str = Form(...),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Kassa, item_id)
    if obj:
        await catalog_service.update_one(session, obj, name=name)
    return RedirectResponse("/catalog/kassy", status_code=303)


@router.post("/catalog/valyuty/{item_id}/update")
async def update_valyuta(
    item_id: int, code: str = Form(...), name: str = Form(...), rate: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Valyuta, item_id)
    if obj:
        obj.code = code
        obj.name = name
        await session.commit()
        if rate.strip():
            await catalog_service.set_rate(session, item_id, date.today(), Decimal(rate))
    return RedirectResponse("/catalog/valyuty", status_code=303)


@router.post("/catalog/edinitsy/{item_id}/update")
async def update_edinitsa(
    item_id: int, name: str = Form(...), short_name: str = Form(...),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Edinitsa, item_id)
    if obj:
        await catalog_service.update_one(session, obj, name=name, short_name=short_name)
    return RedirectResponse("/catalog/edinitsy", status_code=303)


@router.post("/catalog/stavki_nds/{item_id}/update")
async def update_stavka_nds(
    item_id: int, name: str = Form(...), rate: str = Form(...),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.StavkaNDS, item_id)
    if obj:
        await catalog_service.update_one(session, obj, name=name, rate=Decimal(rate))
    return RedirectResponse("/catalog/stavki_nds", status_code=303)


@router.post("/catalog/tipy_tsen/{item_id}/update")
async def update_tip_tsen(
    item_id: int, name: str = Form(...), markup_percent: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.TipTsen, item_id)
    if obj:
        obj.name = name
        obj.markup_percent = _or_decimal(markup_percent)
        await session.commit()
    return RedirectResponse("/catalog/tipy_tsen", status_code=303)


# --- Сотрудники ---


@router.get("/catalog/sotrudniki", response_class=HTMLResponse)
async def catalog_sotrudniki(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    items = await catalog_service.list_all(session, cat.Sotrudnik)
    return _page(request, user, "trade/sotrudniki.html", items=items)


@router.post("/catalog/sotrudniki")
async def create_sotrudnik(
    name: str = Form(...), position: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(session, cat.Sotrudnik, name=name, position=position or None)
    return RedirectResponse("/catalog/sotrudniki", status_code=303)


@router.post("/catalog/sotrudniki/{item_id}/update")
async def update_sotrudnik(
    item_id: int, name: str = Form(...), position: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.Sotrudnik, item_id)
    if obj:
        obj.name = name
        obj.position = position or None
        await session.commit()
    return RedirectResponse("/catalog/sotrudniki", status_code=303)


# --- Расчётные счета ---


@router.get("/catalog/scheta", response_class=HTMLResponse)
async def catalog_scheta(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    items = await catalog_service.list_all(session, cat.RaschetnySchet)
    kontragenty = await catalog_service.list_all(session, cat.Kontragent)
    kg_map = {k.id: k.name for k in kontragenty}
    return _page(request, user, "trade/scheta.html", items=items, kontragenty=kontragenty, kg_map=kg_map)


@router.post("/catalog/scheta")
async def create_schet(
    kontragent_id: str = Form(...), bank_name: str = Form(""), account: str = Form(...),
    bik: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(
        session, cat.RaschetnySchet,
        kontragent_id=int(kontragent_id), bank_name=bank_name or None, account=account, bik=bik or None,
    )
    return RedirectResponse("/catalog/scheta", status_code=303)


@router.post("/catalog/scheta/{item_id}/update")
async def update_schet(
    item_id: int, kontragent_id: str = Form(...), bank_name: str = Form(""),
    account: str = Form(...), bik: str = Form(""),
    session=Depends(get_session), user=Depends(get_current_user_from_cookie),
):
    obj = await catalog_service.get_one(session, cat.RaschetnySchet, item_id)
    if obj:
        obj.kontragent_id = int(kontragent_id)
        obj.bank_name = bank_name or None
        obj.account = account
        obj.bik = bik or None
        await session.commit()
    return RedirectResponse("/catalog/scheta", status_code=303)


# --- Цены номенклатуры (виды цен + автонаценка) ---


@router.post("/catalog/nomenklatura/{item_id}/prices")
async def update_nomenklatura_prices(
    item_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    """Сохраняет закупочную/свободную цену и явные цены по видам цен."""
    obj = await catalog_service.get_one(session, cat.Nomenklatura, item_id)
    if obj is None:
        return RedirectResponse("/catalog/nomenklatura", status_code=303)

    form = await request.form()
    obj.purchase_price = _or_decimal(str(form.get("purchase_price", "") or ""))
    obj.retail_price = _or_decimal(str(form.get("retail_price", "") or ""))

    tipy = await catalog_service.list_all(session, cat.TipTsen)
    for tip in tipy:
        key = f"override_{tip.id}"
        raw = str(form.get(key, "") or "").strip()
        if raw:
            await price_service.set_explicit_price(session, item_id, tip.id, Decimal(raw))
        else:
            await price_service.clear_explicit_price(session, item_id, tip.id)

    await session.commit()
    return RedirectResponse("/catalog/nomenklatura", status_code=303)


# --- РМК (рабочее место кассира) ---


@router.get("/rmk", response_class=HTMLResponse)
async def rmk_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if user.is_admin:
        return RedirectResponse("/admin", status_code=303)
    result = await session.execute(select(cat.Nomenklatura).order_by(cat.Nomenklatura.name))
    nomen = list(result.scalars())
    tipy = await catalog_service.list_all(session, cat.TipTsen)
    tipy_map = {t.id: t for t in tipy}

    items = [
        {
            "id": n.id,
            "name": n.name,
            "price": float(price_service.effective_price(n, tipy_map) or Decimal("0")),
        }
        for n in nomen
    ]
    sklady = await catalog_service.list_all(session, cat.Sklad)
    return _page(
        request, user, "trade/rmk.html",
        items_json=json.dumps(items, ensure_ascii=False),
        sklady=sklady,
    )


@router.post("/rmk/sell")
async def rmk_sell(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    data = await request.json()
    items = data.get("items") or []
    if not items:
        return JSONResponse({"detail": "Накладная пуста"}, status_code=400)

    sklad_id = data.get("sklad_id")
    try:
        document = await document_service.create_document(
            session,
            doc_type=DocType.RASHOD,
            subtype=DocSubtype.CASH,
            doc_date=date.today(),
            sklad_id=sklad_id,
            items=[
                {"nomenklatura_id": int(i["nomenklatura_id"]), "quantity": Decimal(str(i["quantity"])), "price": Decimal(str(i["price"]))}
                for i in items
            ],
            created_by_id=user.id,
        )
        await document_service.post_document(session, document)
    except InsufficientStockError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=409)
    except document_service.DocumentError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return {"id": document.id}


# --- Печатная форма накладной ---


@router.get("/documents/{document_id}/print", response_class=HTMLResponse)
async def document_print(
    document_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    document = await document_service.get_document(session, document_id)
    if document is None:
        return _page(request, user, "trade/error.html", error="Документ не найден", back="/documents")
    names = await _resolve_names(session, document)
    return _page(request, user, "trade/invoice.html", document=document, names=names)


# --- Заявки покупателя ---


@router.get("/zakazy", response_class=HTMLResponse)
async def zakazy_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    stmt = (
        select(Document)
        .where(Document.doc_type == DocType.ZAKAZ.value)
        .order_by(Document.date.desc(), Document.id.desc())
    )
    result = await session.execute(stmt)
    zakazy = list(result.scalars())
    kontragenty = await catalog_service.list_all(session, cat.Kontragent)
    nomen = await catalog_service.list_all(session, cat.Nomenklatura)
    kg_map = {k.id: k.name for k in kontragenty}
    return _page(
        request, user, "trade/zakazy.html",
        zakazy=zakazy, kontragenty=kontragenty, nomen=nomen, kg_map=kg_map,
        ZAKAZ_STATES=ZAKAZ_STATES, today=date.today().isoformat(),
    )


@router.post("/zakazy")
async def zakaz_create(
    request: Request,
    kontragent_id: str = Form(...),
    doc_date: str = Form(...),
    comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    form = await request.form()
    items = _parse_items(form)
    await document_service.create_document(
        session,
        doc_type=DocType.ZAKAZ,
        doc_date=date.fromisoformat(doc_date),
        kontragent_id=int(kontragent_id),
        comment=comment or None,
        extra={"state": "new"},
        items=items,
        created_by_id=user.id,
    )
    return RedirectResponse("/zakazy", status_code=303)


@router.post("/zakazy/{zakaz_id}/state")
async def zakaz_state(
    zakaz_id: int,
    state: str = Form(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    doc = await document_service.get_document(session, zakaz_id)
    if doc:
        extra = dict(doc.extra or {})
        extra["state"] = state if state in ZAKAZ_STATES else "new"
        doc.extra = extra
        await session.commit()
        # При выполнении/отмене — снимаем резерв.
        if state in ("done", "cancelled"):
            await stock_service.release_for_zakaz(session, zakaz_id)
            await session.commit()
    return RedirectResponse("/zakazy", status_code=303)


@router.post("/zakazy/{zakaz_id}/reserve")
async def zakaz_reserve(
    zakaz_id: int,
    sklad_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    """Резервирует товар по заявке на складе (по умолчанию — основной склад)."""
    zakaz = await document_service.get_document(session, zakaz_id)
    if zakaz and zakaz.items:
        sklady = await catalog_service.list_all(session, cat.Sklad)
        target = (
            int(sklad_id)
            if sklad_id
            else next((s.id for s in sklady if s.is_default), sklady[0].id if sklady else None)
        )
        if target is not None:
            await stock_service.release_for_zakaz(session, zakaz_id)
            try:
                for item in zakaz.items:
                    await stock_service.reserve(
                        session,
                        nomenklatura_id=item.nomenklatura_id,
                        sklad_id=target,
                        quantity=item.quantity,
                        zakaz_id=zakaz_id,
                    )
                await session.commit()
            except InsufficientStockError:
                await session.rollback()
    return RedirectResponse("/zakazy", status_code=303)


# --- Договоры контрагентов ---


@router.get("/dogovory", response_class=HTMLResponse)
async def dogovory_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    dogovory = await catalog_service.list_all(session, cat.Dogovor)
    kontragenty = await catalog_service.list_all(session, cat.Kontragent)
    kg_map = {k.id: k.name for k in kontragenty}
    return _page(request, user, "trade/dogovory.html", dogovory=dogovory, kontragenty=kontragenty, kg_map=kg_map)


@router.post("/dogovory")
async def dogovor_create(
    kontragent_id: str = Form(...), name: str = Form(...), number: str = Form(""),
    payment_term_days: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    await catalog_service.create_one(
        session, cat.Dogovor,
        kontragent_id=int(kontragent_id), name=name, number=number or None,
        payment_term_days=int(payment_term_days) if payment_term_days else None,
    )
    return RedirectResponse("/dogovory", status_code=303)


# --- Инвентаризация ---


@router.get("/inventarizaciya", response_class=HTMLResponse)
async def inventarizaciya_form(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    balances = await report_service.stock_balances(session)
    sklady = await catalog_service.list_all(session, cat.Sklad)
    return _page(request, user, "trade/inventarizaciya.html", balances=balances, sklady=sklady)


@router.post("/inventarizaciya")
async def inventarizaciya_submit(
    request: Request,
    sklad_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    form = await request.form()
    items = []
    for key, value in form.items():
        if not key.startswith("actual_"):
            continue
        parts = key.split("_")  # actual_{nomen_id}_{sklad_id}
        if len(parts) < 3:
            continue
        nomen_id = int(parts[1])
        item_sklad = int(parts[2])
        if not value.strip():
            continue
        actual = Decimal(value)
        items.append(
            {"nomenklatura_id": nomen_id, "sklad_id": item_sklad, "quantity": actual, "price": Decimal("0")}
        )

    if not items:
        return RedirectResponse("/inventarizaciya", status_code=303)

    document = await document_service.create_document(
        session,
        doc_type=DocType.INVENTARIZACIYA,
        doc_date=date.today(),
        sklad_id=int(sklad_id) if sklad_id else None,
        items=items,
        created_by_id=user.id,
    )
    await document_service.post_document(session, document)
    return RedirectResponse("/documents", status_code=303)


# --- Документы ---


@router.get("/documents", response_class=HTMLResponse)
async def documents_journal(
    request: Request,
    doc_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    stmt = select(Document).order_by(Document.date.desc(), Document.id.desc())
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if start:
        stmt = stmt.where(Document.date >= date.fromisoformat(start))
    if end:
        stmt = stmt.where(Document.date <= date.fromisoformat(end))
    if status:
        stmt = stmt.where(Document.status == status)
    result = await session.execute(stmt)
    documents = list(result.scalars())
    # Карта наименований контрагентов и складов для отображения.
    kg = await catalog_service.list_all(session, cat.Kontragent)
    sk = await catalog_service.list_all(session, cat.Sklad)
    kg_map = {k.id: k.name for k in kg}
    sk_map = {s.id: s.name for s in sk}
    return _page(
        request, user, "trade/documents.html",
        documents=documents, doc_type=doc_type, start=start, end=end, status=status,
        kg_map=kg_map, sk_map=sk_map,
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
    nds = await catalog_service.list_all(session, cat.StavkaNDS)
    return _page(
        request, user, "trade/document_form.html",
        doc_type=doc_type, nomenklatura=nomenklatura, sklady=sklady,
        kontragenty=kontragenty, kassy=kassy, firmy=firmy, nds=nds,
        today=date.today().isoformat(),
        is_item_doc=doc_type in _ITEM_DOCS,
        is_money_doc=doc_type in _MONEY_DOCS,
        label=DOC_LABELS.get(doc_type, doc_type),
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
        return _page(request, user, "trade/error.html", error=str(exc), back="/documents")
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


@router.get("/documents/{document_id}", response_class=HTMLResponse)
async def document_detail(
    document_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    document = await document_service.get_document(session, document_id)
    if document is None:
        return _page(request, user, "trade/error.html", error="Документ не найден", back="/documents")
    names = await _resolve_names(session, document)
    return _page(request, user, "trade/document_detail.html", document=document, names=names)


async def _resolve_names(session: AsyncSession, document: Document) -> dict:
    """Подставляет наименования для отображения документа."""
    names: dict = {"items": []}
    nomen = await catalog_service.list_all(session, cat.Nomenklatura)
    sklady = await catalog_service.list_all(session, cat.Sklad)
    kg = await catalog_service.list_all(session, cat.Kontragent)
    nomen_map = {n.id: n.name for n in nomen}
    sklad_map = {s.id: s.name for s in sklady}
    kg_map = {k.id: k.name for k in kg}
    names["sklad"] = sklad_map.get(document.sklad_id) if document.sklad_id else None
    names["sklad_to"] = sklad_map.get(document.sklad_to_id) if document.sklad_to_id else None
    names["kontragent"] = kg_map.get(document.kontragent_id) if document.kontragent_id else None
    for item in document.items:
        names["items"].append(
            {
                "name": nomen_map.get(item.nomenklatura_id, f"#{item.nomenklatura_id}"),
                "quantity": item.quantity,
                "price": item.price,
                "amount": item.amount,
            }
        )
    return names


@router.post("/documents/{document_id}/post")
async def document_post(document_id: int, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    document = await document_service.get_document(session, document_id)
    if document:
        try:
            await document_service.post_document(session, document)
        except (InsufficientStockError, document_service.DocumentError):
            pass
    return RedirectResponse("/documents", status_code=303)


@router.post("/documents/{document_id}/unpost")
async def document_unpost(document_id: int, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    document = await document_service.get_document(session, document_id)
    if document:
        await document_service.unpost_document(session, document)
    return RedirectResponse("/documents", status_code=303)


@router.post("/documents/{document_id}/delete")
async def document_delete(document_id: int, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    document = await document_service.get_document(session, document_id)
    if document:
        await document_service.mark_for_deletion(session, document)
    return RedirectResponse("/documents", status_code=303)


# --- Отчёты ---


@router.get("/reports", response_class=HTMLResponse)
async def reports_index(request: Request, user: User = Depends(get_current_user_from_cookie)):
    return _page(request, user, "trade/reports.html")


@router.get("/reports/stock", response_class=HTMLResponse)
async def report_stock(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    balances = await report_service.stock_balances(session)
    return _page(request, user, "trade/report_stock.html", balances=balances)


@router.get("/reports/movements", response_class=HTMLResponse)
async def report_movements(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    s, e = _month_range() if not (start and end) else (start, end)
    rows = await report_service.stock_movements(session, date.fromisoformat(s), date.fromisoformat(e))
    return _page(request, user, "trade/report_movements.html", rows=rows, start=s, end=e)


@router.get("/reports/sales", response_class=HTMLResponse)
async def report_sales(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    s, e = _month_range() if not (start and end) else (start, end)
    rows = await report_service.sales_report(session, date.fromisoformat(s), date.fromisoformat(e))
    total = sum((r["total"] for r in rows), Decimal("0"))
    return _page(request, user, "trade/report_sales.html", rows=rows, start=s, end=e, total=total)


@router.get("/reports/settlements", response_class=HTMLResponse)
async def report_settlements(request: Request, session=Depends(get_session), user=Depends(get_current_user_from_cookie)):
    rows = await report_service.settlement_balances(session)
    return _page(request, user, "trade/report_settlements.html", rows=rows)


@router.get("/reports/money", response_class=HTMLResponse)
async def report_money(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    balance = await report_service.money_balance(session)
    s, e = _month_range() if not (start and end) else (start, end)
    rows = await report_service.money_movements(session, date.fromisoformat(s), date.fromisoformat(e))
    return _page(request, user, "trade/report_money.html", balance=balance, rows=rows, start=s, end=e)


@router.get("/reports/settlement-movements", response_class=HTMLResponse)
async def report_settlement_movements(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    kontragent_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    s, e = _month_range() if not (start and end) else (start, end)
    rows = await report_service.settlement_movements(
        session, date.fromisoformat(s), date.fromisoformat(e),
        int(kontragent_id) if kontragent_id else None,
    )
    kontragenty = await catalog_service.list_all(session, cat.Kontragent)
    return _page(
        request, user, "trade/report_settlement_movements.html",
        rows=rows, start=s, end=e, kontragenty=kontragenty, kontragent_id=kontragent_id,
    )


@router.get("/reports/abc", response_class=HTMLResponse)
async def report_abc(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    s, e = _month_range() if not (start and end) else (start, end)
    rows = await report_service.abc_analysis(session, date.fromisoformat(s), date.fromisoformat(e))
    return _page(request, user, "trade/report_abc.html", rows=rows, start=s, end=e)


@router.get("/reports/accounting", response_class=HTMLResponse)
async def report_accounting(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    s, e = _month_range() if not (start and end) else (start, end)
    rows = await report_service.accounting_entries(session, date.fromisoformat(s), date.fromisoformat(e))
    total = sum((r["amount"] for r in rows), Decimal("0"))
    return _page(request, user, "trade/report_accounting.html", rows=rows, start=s, end=e, total=total)


@router.get("/reports/commission", response_class=HTMLResponse)
async def report_commission(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    data = await report_service.commission_report(session)
    return _page(request, user, "trade/report_commission.html", data=data)
