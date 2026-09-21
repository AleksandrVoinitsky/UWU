"""Документы: создание, проведение, отмена проведения.

Проведение — центральная операция системы: проверяет контроль остатков,
формирует движения по регистрам (товары, партии, деньги, взаиморасчёты) и
устанавливает статус «Проведён».

См. также: :mod:`app.services.stock_service`, :mod:`app.models.document.base_document`,
:mod:`app.models.registry`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.constants import Constant
from app.models.document.base_document import Document, DocumentItem
from app.models.enums import CostMethod, DocSubtype, DocType, DocumentStatus, RestockControl
from app.models.registry import MoneyMovement, SettlementMovement, StockMovement
from app.services import stock_service
from app.services.stock_service import InsufficientStockError

# Виды документов, порождающие движение товара.
_STOCK_DOC_TYPES = {
    DocType.PRIHOD,
    DocType.RASHOD,
    DocType.PEREMESHENIE,
    DocType.SPISANIE,
    DocType.OPRIHODOVANIE,
    DocType.VVOD_OSTATKOV,
    DocType.VOZVRAT,
}

# Документы прихода (формируют партии).
_INCOMING = {DocType.PRIHOD, DocType.OPRIHODOVANIE, DocType.VVOD_OSTATKOV, DocType.VOZVRAT}


class DocumentError(Exception):
    """Ошибка валидации документа."""


async def next_document_number(session: AsyncSession, doc_type: DocType) -> str:
    """Генерирует следующий номер документа (с префиксом ИБ)."""
    prefix = await _get_prefix(session)
    base = f"{prefix}{doc_type.value[:2].upper()}"
    stmt = select(func.count(Document.id)).where(Document.doc_type == doc_type.value)
    count = (await session.execute(stmt)).scalar() or 0
    return f"{base}-{count + 1:05d}"


async def _get_prefix(session: AsyncSession) -> str:
    result = await session.execute(select(Constant).where(Constant.key == "prefix_ib"))
    constant = result.scalar_one_or_none()
    return (constant.value if constant and constant.value else "") or ""


async def _get_cost_method(session: AsyncSession) -> CostMethod:
    result = await session.execute(select(Constant).where(Constant.key == "cost_method"))
    constant = result.scalar_one_or_none()
    value = constant.value if constant else None
    try:
        return CostMethod(value or "fifo")
    except ValueError:
        return CostMethod.FIFO


async def _get_restock_control(session: AsyncSession) -> RestockControl:
    result = await session.execute(select(Constant).where(Constant.key == "restock_control"))
    constant = result.scalar_one_or_none()
    value = constant.value if constant else None
    try:
        return RestockControl(value or "by_warehouse")
    except ValueError:
        return RestockControl.BY_WAREHOUSE


def _compute_item_amounts(item: DocumentItem, nds_rate_percent: Decimal | None) -> None:
    """Пересчитывает сумму и НДС строки (без lazy-load отношений)."""
    item.amount = (item.quantity * item.price).quantize(Decimal("0.01"))
    if item.nds_rate_id is not None and nds_rate_percent is not None:
        item.nds_amount = (item.amount * nds_rate_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )
    else:
        item.nds_amount = Decimal("0")


async def _load_nds_rates(session: AsyncSession) -> dict[int, Decimal]:
    """Загружает ставки НДС {id: процент} для расчёта строк."""
    from app.models.catalog import StavkaNDS

    result = await session.execute(select(StavkaNDS))
    return {s.id: s.rate for s in result.scalars()}


async def _load_items(session: AsyncSession, document: Document) -> list[DocumentItem]:
    """Загружает строки документа явным запросом (без lazy-load)."""
    result = await session.execute(
        select(DocumentItem)
        .where(DocumentItem.document_id == document.id)
        .order_by(DocumentItem.id)
    )
    return list(result.scalars())


async def create_document(
    session: AsyncSession,
    *,
    doc_type: DocType,
    doc_date: date,
    subtype: DocSubtype | None = None,
    number: str | None = None,
    firma_id: int | None = None,
    kontragent_id: int | None = None,
    dogovor_id: int | None = None,
    sklad_id: int | None = None,
    sklad_to_id: int | None = None,
    kassa_id: int | None = None,
    valyuta_id: int | None = None,
    comment: str | None = None,
    extra: dict | None = None,
    total: Decimal | None = None,
    items: list[dict] | None = None,
    created_by_id: int | None = None,
) -> Document:
    """Создаёт документ со строками и пересчитывает итоги.

    ``total`` используется для денежных документов без табличной части.
    """
    document = Document(
        doc_type=doc_type,
        subtype=subtype.value if subtype else None,
        number=number or await next_document_number(session, doc_type),
        date=doc_date,
        firma_id=firma_id,
        kontragent_id=kontragent_id,
        dogovor_id=dogovor_id,
        sklad_id=sklad_id,
        sklad_to_id=sklad_to_id,
        kassa_id=kassa_id,
        valyuta_id=valyuta_id,
        comment=comment,
        extra=extra or {},
        created_by_id=created_by_id,
    )
    session.add(document)
    await session.flush()

    nds_rates = await _load_nds_rates(session)
    item_objs: list[DocumentItem] = []
    for row in items or []:
        item = DocumentItem(
            document_id=document.id,
            nomenklatura_id=row["nomenklatura_id"],
            sklad_id=row.get("sklad_id") or sklad_id,
            quantity=row["quantity"],
            price=row["price"],
            amount=Decimal("0"),
            nds_rate_id=row.get("nds_rate_id"),
        )
        session.add(item)
        item_objs.append(item)
        await session.flush()
        _compute_item_amounts(item, nds_rates.get(item.nds_rate_id) if item.nds_rate_id else None)

    if total is not None:
        document.total = total
    else:
        _recalc_totals(document, item_objs)
    await session.commit()
    return await get_document(session, document.id)


def _recalc_totals(document: Document, items: list[DocumentItem]) -> None:
    document.total = sum((i.amount for i in items), Decimal("0")).quantize(
        Decimal("0.01")
    )
    document.nds_total = sum(
        (i.nds_amount for i in items), Decimal("0")
    ).quantize(Decimal("0.01"))


async def get_document(session: AsyncSession, document_id: int) -> Document | None:
    """Возвращает документ с явно загруженными строками (без lazy-load)."""
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.items))
        .where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


async def post_document(session: AsyncSession, document: Document) -> Document:
    """Проводит документ: контроль остатков + формирование движений."""
    if document.status == DocumentStatus.POSTED:
        return document
    if document.status == DocumentStatus.MARKED_DELETED:
        raise DocumentError("Cannot post a document marked for deletion")

    doc_type = DocType(document.doc_type)

    if doc_type in _STOCK_DOC_TYPES:
        items = await _load_items(session, document)
        if not items:
            raise DocumentError("Document has no items")

        restock = await _get_restock_control(session)

        if doc_type == DocType.RASHOD and restock != RestockControl.NONE:
            await _check_stock(session, document, items, restock)

        cost_method = await _get_cost_method(session)

        for item in items:
            await _apply_stock_movement(session, document, item, doc_type, cost_method)

    await _apply_money_and_settlement(session, document, doc_type)

    document.status = DocumentStatus.POSTED
    document.posted_at = datetime.now(timezone.utc)
    await session.commit()
    return await get_document(session, document.id)


async def _check_stock(
    session: AsyncSession,
    document: Document,
    items: list[DocumentItem],
    restock: RestockControl,
) -> None:
    """Проверяет достаточность остатков перед расходом."""
    for item in items:
        sklad_id = item.sklad_id if restock == RestockControl.BY_WAREHOUSE else None
        balance = await stock_service.get_balance(session, item.nomenklatura_id, sklad_id)
        if balance < item.quantity:
            raise InsufficientStockError(
                nomenklatura_id=item.nomenklatura_id,
                sklad_id=item.sklad_id,
                available=balance,
                required=item.quantity,
            )


async def _apply_stock_movement(
    session: AsyncSession,
    document: Document,
    item: DocumentItem,
    doc_type: DocType,
    cost_method: CostMethod,
) -> None:
    """Применяет движение товара по строке документа."""
    source_sklad = item.sklad_id or document.sklad_id
    if source_sklad is None:
        raise DocumentError("Warehouse is required for stock documents")

    if doc_type in _INCOMING:
        await stock_service.create_incoming(
            session,
            document_id=document.id,
            date=document.date,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            price=item.price,
        )
    elif doc_type == DocType.PEREMESHENIE:
        target_sklad = document.sklad_to_id
        if target_sklad is None:
            raise DocumentError("Target warehouse is required for transfer")
        consumed, amount = await stock_service.consume_batches(
            session,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            method=cost_method,
        )
        await stock_service.register_outgoing(
            session,
            document_id=document.id,
            date=document.date,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            amount=amount,
        )
        unit_cost = (amount / item.quantity).quantize(Decimal("0.0001")) if item.quantity else Decimal("0")
        await stock_service.create_incoming(
            session,
            document_id=document.id,
            date=document.date,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=target_sklad,
            quantity=item.quantity,
            price=unit_cost,
        )
    else:  # RASHOD, SPISANIE — расход
        consumed, amount = await stock_service.consume_batches(
            session,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            method=cost_method,
        )
        await stock_service.register_outgoing(
            session,
            document_id=document.id,
            date=document.date,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            amount=amount,
        )


async def _apply_money_and_settlement(
    session: AsyncSession, document: Document, doc_type: DocType
) -> None:
    """Формирует движения денег и взаиморасчётов."""
    subtype = DocSubtype(document.subtype) if document.subtype else None

    # Взаиморасчёты по товарным накладным (кроме наличных).
    if doc_type == DocType.RASHOD and subtype in (DocSubtype.CREDIT, DocSubtype.REALIZATION):
        if document.kontragent_id:
            session.add(
                SettlementMovement(
                    document_id=document.id,
                    date=document.date,
                    kontragent_id=document.kontragent_id,
                    dogovor_id=document.dogovor_id,
                    amount=document.total,
                )
            )
    elif doc_type == DocType.PRIHOD and subtype in (DocSubtype.CREDIT, DocSubtype.REALIZATION):
        if document.kontragent_id:
            session.add(
                SettlementMovement(
                    document_id=document.id,
                    date=document.date,
                    kontragent_id=document.kontragent_id,
                    dogovor_id=document.dogovor_id,
                    amount=-document.total,
                )
            )

    # Денежные документы.
    if doc_type == DocType.PRIHODNY_KASSOVY_ORDER:
        session.add(
            MoneyMovement(
                document_id=document.id,
                date=document.date,
                kassa_id=document.kassa_id,
                kontragent_id=document.kontragent_id,
                amount=document.total,
            )
        )
        if document.kontragent_id:
            session.add(
                SettlementMovement(
                    document_id=document.id,
                    date=document.date,
                    kontragent_id=document.kontragent_id,
                    dogovor_id=document.dogovor_id,
                    amount=-document.total,
                )
            )
    elif doc_type in (DocType.RASHODNY_KASSOVY_ORDER, DocType.PLATEZHNOE_PORUCHENIE):
        session.add(
            MoneyMovement(
                document_id=document.id,
                date=document.date,
                kassa_id=document.kassa_id,
                kontragent_id=document.kontragent_id,
                amount=-document.total,
            )
        )
        if document.kontragent_id:
            session.add(
                SettlementMovement(
                    document_id=document.id,
                    date=document.date,
                    kontragent_id=document.kontragent_id,
                    dogovor_id=document.dogovor_id,
                    amount=document.total,
                )
            )
    elif doc_type == DocType.VVOD_OSTATKOV_DENEG:
        session.add(
            MoneyMovement(
                document_id=document.id,
                date=document.date,
                kassa_id=document.kassa_id,
                amount=document.total,
            )
        )


async def unpost_document(session: AsyncSession, document: Document) -> Document:
    """Отменяет проведение: удаляет движения и восстанавливает партии."""
    if document.status != DocumentStatus.POSTED:
        return document

    doc_type = DocType(document.doc_type)

    if doc_type in _STOCK_DOC_TYPES:
        await _rollback_stock(session, document)

    # Удаляем движения денег и взаиморасчётов.
    await _delete_movements(session, document.id)

    document.status = DocumentStatus.DRAFT
    document.posted_at = None
    await session.commit()
    return await get_document(session, document.id)


async def _delete_movements(session: AsyncSession, document_id: int) -> None:
    for model in (MoneyMovement, SettlementMovement):
        result = await session.execute(
            select(model).where(model.document_id == document_id)
        )
        for row in result.scalars():
            await session.delete(row)


async def _rollback_stock(session: AsyncSession, document: Document) -> None:
    """Восстанавливает партии при отмене проведения (обратные движения)."""
    doc_type = DocType(document.doc_type)

    # Удаляем движения товара.
    result = await session.execute(
        select(StockMovement).where(StockMovement.document_id == document.id)
    )
    movements = list(result.scalars())

    if doc_type in _INCOMING:
        # Возврат прихода: уменьшаем партии, созданные документом.
        for movement in movements:
            if movement.batch_id:
                batch = await session.get(stock_service.StockBatch, movement.batch_id)
                if batch:
                    batch.quantity -= movement.quantity
    else:
        # Расход/перемещение: восстанавливаем списанные партии обратным способом.
        # Для простоты создаём новую партию с той же себестоимостью.
        for movement in movements:
            if movement.quantity < 0:
                unit_cost = (
                    (-movement.amount / -movement.quantity).quantize(Decimal("0.0001"))
                    if movement.quantity
                    else Decimal("0")
                )
                batch = stock_service.StockBatch(
                    nomenklatura_id=movement.nomenklatura_id,
                    sklad_id=movement.sklad_id,
                    quantity=-movement.quantity,
                    unit_cost=unit_cost,
                    source_document_id=document.id,
                )
                session.add(batch)
            else:
                # Приход внутри перемещения — убираем созданную партию.
                if movement.batch_id:
                    batch = await session.get(stock_service.StockBatch, movement.batch_id)
                    if batch:
                        batch.quantity -= movement.quantity

    for movement in movements:
        await session.delete(movement)


async def mark_for_deletion(session: AsyncSession, document: Document) -> Document:
    """Помечает документ на удаление (после отмены проведения)."""
    if document.status == DocumentStatus.POSTED:
        await unpost_document(session, document)
    document.status = DocumentStatus.MARKED_DELETED
    await session.commit()
    return await get_document(session, document.id)
