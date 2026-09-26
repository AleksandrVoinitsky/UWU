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

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.constants import Constant
from app.models.document.base_document import Document, DocumentItem
from app.models.enums import CostMethod, DocSubtype, DocType, DocumentStatus, RestockControl
from app.models.registry import (
    AccountingEntry,
    AuditLog,
    MoneyMovement,
    SettlementMovement,
    StockBatch,
    StockMovement,
)
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
    DocType.INVENTARIZACIYA,
}

# Документы прихода (формируют партии).
_INCOMING = {DocType.PRIHOD, DocType.OPRIHODOVANIE, DocType.VVOD_OSTATKOV, DocType.VOZVRAT}


def _log(
    session: AsyncSession,
    document: Document,
    action: str,
    user_id: int | None = None,
) -> None:
    """Записывает действие над документом в журнал (история изменений).

    ``user_id`` — пользователь, выполнивший действие; если не передан,
    используется автор документа (``created_by_id``).
    """
    session.add(
        AuditLog(
            user_id=user_id if user_id is not None else document.created_by_id,
            entity_type="document",
            entity_id=document.id,
            action=action,
        )
    )


class DocumentError(Exception):
    """Ошибка валидации документа."""


# Пространство advisory-lock PostgreSQL для нумерации документов.
# Защищает от гонок при одновременном создании документов одного вида.
_DOCNUM_LOCK_NAMESPACE = 42

# Пространство advisory-lock для проведения/отмены проведения документа.
# Сериализует параллельные post/unpost одного документа (защита от
# двойного проведения и гонок при отмене).
_POST_LOCK_NAMESPACE = 43


async def next_document_number(session: AsyncSession, doc_type: DocType) -> str:
    """Генерирует следующий номер документа (с префиксом ИБ).

    Номер считается от максимального существующего (а не от количества строк),
    чтобы после удаления документов не возникало дублей. Конкурентные вызовы
    сериализуются advisory-lock'ом PostgreSQL, удерживаемым до конца транзакции.
    """
    prefix = await _get_prefix(session)
    # Полное имя вида документа, а не первые 2 буквы: у PEREOCENKA/PEREMESHENIE
    # и VVOD_OSTATKOV/VVOD_OSTATKOV_DENEG общий 2-символьный префикс, из-за
    # чего возникали коллизии номеров в журналах.
    base = f"{prefix}{doc_type.value.upper()}"

    # Сериализуем генерацию номера на время транзакции.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
        {"ns": _DOCNUM_LOCK_NAMESPACE, "key": f"uwu_docnum_{doc_type.value}"},
    )

    stmt = select(func.max(Document.number)).where(Document.doc_type == doc_type.value)
    max_number = (await session.execute(stmt)).scalar()
    last = 0
    if max_number:
        try:
            last = int(str(max_number).rsplit("-", 1)[1])
        except (ValueError, IndexError):
            last = 0
    return f"{base}-{last + 1:05d}"


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


async def update_document_items(
    session: AsyncSession, document: Document, items: list[dict]
) -> Document:
    """Заменяет строки документа (только для непроведённого) и пересчитывает итоги."""
    if document.status == DocumentStatus.POSTED:
        raise DocumentError("Cannot edit items of a posted document")

    existing = await _load_items(session, document)
    for item in existing:
        await session.delete(item)
    await session.flush()

    nds_rates = await _load_nds_rates(session)
    item_objs: list[DocumentItem] = []
    for row in items:
        item = DocumentItem(
            document_id=document.id,
            nomenklatura_id=row["nomenklatura_id"],
            sklad_id=row.get("sklad_id") or document.sklad_id,
            quantity=row["quantity"],
            price=row["price"],
            amount=Decimal("0"),
            nds_rate_id=row.get("nds_rate_id"),
        )
        session.add(item)
        item_objs.append(item)
        await session.flush()
        _compute_item_amounts(item, nds_rates.get(item.nds_rate_id) if item.nds_rate_id else None)

    _recalc_totals(document, item_objs)
    await session.commit()

    # Перезагружаем документ со строками (identity map может хранить устаревшие строки).
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.items))
        .where(Document.id == document.id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def post_document(
    session: AsyncSession, document: Document, user_id: int | None = None
) -> Document:
    """Проводит документ: контроль остатков + формирование движений."""
    # Сериализуем проведение документа: параллельный запрос на тот же документ
    # заблокируется здесь до завершения текущего (защита от двойного проведения).
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :key)"),
        {"ns": _POST_LOCK_NAMESPACE, "key": document.id},
    )
    # Перечитываем актуальный статус под блокировкой — другой поток мог уже
    # провести документ, пока мы ждали блокировку.
    status_row = (
        await session.execute(
            select(Document.status).where(Document.id == document.id)
        )
    ).scalar_one_or_none()
    if status_row == DocumentStatus.POSTED:
        return await get_document(session, document.id)
    if status_row == DocumentStatus.MARKED_DELETED:
        raise DocumentError("Cannot post a document marked for deletion")

    doc_type = DocType(document.doc_type)

    try:
        if doc_type in _STOCK_DOC_TYPES:
            items = await _load_items(session, document)
            if not items:
                raise DocumentError("Document has no items")

            restock = await _get_restock_control(session)

            if doc_type == DocType.RASHOD and restock != RestockControl.NONE:
                await _check_stock(session, document, items, restock)

            cost_method = await _get_cost_method(session)

            if doc_type == DocType.INVENTARIZACIYA:
                await _apply_inventory(session, document, items, cost_method)
            else:
                for item in items:
                    await _apply_stock_movement(
                        session, document, item, doc_type, cost_method, restock
                    )

        # Переоценка товаров: не меняет количество, а переоценивает учётную
        # стоимость партий (разница отражается проводкой).
        if doc_type == DocType.PEREOCENKA:
            items = await _load_items(session, document)
            if not items:
                raise DocumentError("Document has no items")
            await _apply_revaluation(session, document, items)

        await _apply_money_and_settlement(session, document, doc_type)
        await _apply_accounting(session, document, doc_type)

        document.status = DocumentStatus.POSTED
        document.posted_at = datetime.now(timezone.utc)
        _log(session, document, "post", user_id=user_id)
        await session.commit()
    except Exception:
        # Явный откат: не оставляем сессию в «грязном» состоянии и снимаем
        # advisory-lock до завершения обработки ошибки.
        await session.rollback()
        raise
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
        balance = await stock_service.get_available(session, item.nomenklatura_id, sklad_id)
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
    restock: RestockControl,
) -> None:
    """Применяет движение товара по строке документа."""
    source_sklad = item.sklad_id or document.sklad_id
    if source_sklad is None:
        raise DocumentError("Warehouse is required for stock documents")

    # Разрешаем отрицательный остаток при продаже, когда контроль отключён
    # (NONE) или ведётся по фирме (BY_FIRM): в этих режимах недостаток на
    # конкретном складе не должен блокировать отгрузку.
    allow_negative = doc_type == DocType.RASHOD and restock in (
        RestockControl.NONE,
        RestockControl.BY_FIRM,
    )

    if doc_type in _INCOMING:
        # Принятые на реализацию учитываются раздельно (не собственность).
        ownership = "received" if (doc_type == DocType.PRIHOD and document.subtype == "realization") else "own"
        await stock_service.create_incoming(
            session,
            document_id=document.id,
            date=document.date,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            price=item.price,
            ownership=ownership,
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
            consumed=consumed,
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
            allow_negative=allow_negative,
            source_document_id=document.id,
        )
        await stock_service.register_outgoing(
            session,
            document_id=document.id,
            date=document.date,
            nomenklatura_id=item.nomenklatura_id,
            sklad_id=source_sklad,
            quantity=item.quantity,
            amount=amount,
            consumed=consumed,
        )


async def _apply_inventory(
    session: AsyncSession,
    document: Document,
    items: list[DocumentItem],
    cost_method: CostMethod,
) -> None:
    """Инвентаризация: корректирует остатки до фактического количества.

    ``item.quantity`` — фактическое количество; отклонение = факт − учёт.
    Излишек оприходуется, недостача списывается.
    """
    for item in items:
        sklad = item.sklad_id or document.sklad_id
        if sklad is None:
            raise DocumentError("Склад обязателен для инвентаризации")
        book = await stock_service.get_balance(session, item.nomenklatura_id, sklad)
        deviation = item.quantity - book
        if deviation > 0:
            # Излишек — оприходование.
            await stock_service.create_incoming(
                session,
                document_id=document.id,
                date=document.date,
                nomenklatura_id=item.nomenklatura_id,
                sklad_id=sklad,
                quantity=deviation,
                price=item.price or Decimal("0"),
            )
        elif deviation < 0:
            # Недостача — списание.
            consumed, amount = await stock_service.consume_batches(
                session,
                nomenklatura_id=item.nomenklatura_id,
                sklad_id=sklad,
                quantity=-deviation,
                method=cost_method,
            )
            await stock_service.register_outgoing(
                session,
                document_id=document.id,
                date=document.date,
                nomenklatura_id=item.nomenklatura_id,
                sklad_id=sklad,
                quantity=-deviation,
                amount=amount,
                consumed=consumed,
            )


async def _apply_revaluation(
    session: AsyncSession, document: Document, items: list[DocumentItem]
) -> None:
    """Переоценка товаров: меняет учётную стоимость партий без изменения количества.

    Разница стоимости отражается проводкой (дооценка → Дт 41 / Кт 91.1,
    уценка → Дт 91.2 / Кт 41). Исходные цены сохраняются в ``extra`` для
    корректной отмены проведения.
    """
    reval_log: list[dict] = []
    total_diff = Decimal("0")
    for item in items:
        sklad = item.sklad_id or document.sklad_id
        if sklad is None:
            raise DocumentError("Склад обязателен для переоценки")
        new_price = item.price
        result = await session.execute(
            select(StockBatch)
            .where(
                StockBatch.nomenklatura_id == item.nomenklatura_id,
                StockBatch.sklad_id == sklad,
                StockBatch.quantity != 0,
            )
            .with_for_update()
        )
        batches = list(result.scalars())
        for batch in batches:
            reval_log.append({"batch_id": batch.id, "old_unit_cost": str(batch.unit_cost)})
            total_diff += (new_price - batch.unit_cost) * batch.quantity
            batch.unit_cost = new_price

    # Сохраняем историю для отмены проведения.
    extra = dict(document.extra or {})
    extra["_revaluation"] = reval_log
    document.extra = extra

    if total_diff > 0:
        session.add(
            AccountingEntry(
                document_id=document.id,
                date=document.date,
                account_debit="41",
                account_credit="91.1",
                amount=total_diff.quantize(Decimal("0.01")),
            )
        )
    elif total_diff < 0:
        session.add(
            AccountingEntry(
                document_id=document.id,
                date=document.date,
                account_debit="91.2",
                account_credit="41",
                amount=(-total_diff).quantize(Decimal("0.01")),
            )
        )


async def _rollback_revaluation(session: AsyncSession, document: Document) -> None:
    """Восстанавливает исходные учётные цены партий при отмене переоценки."""
    reval_log = (document.extra or {}).get("_revaluation") or []
    for record in reval_log:
        batch = await session.get(StockBatch, record["batch_id"])
        if batch is not None:
            batch.unit_cost = Decimal(record["old_unit_cost"])


async def _apply_money_and_settlement(
    session: AsyncSession, document: Document, doc_type: DocType
) -> None:
    """Формирует движения денег и взаиморасчётов."""
    subtype = DocSubtype(document.subtype) if document.subtype else None
    # Основание (для оплат — погашаемая накладная).
    base_document_id = (document.extra or {}).get("base_document_id")

    # Взаиморасчёты по товарным накладным (кроме наличных).
    if doc_type == DocType.RASHOD and subtype in (DocSubtype.CREDIT, DocSubtype.REALIZATION):
        if document.kontragent_id:
            session.add(
                SettlementMovement(
                    document_id=document.id,
                    date=document.date,
                    kontragent_id=document.kontragent_id,
                    dogovor_id=document.dogovor_id,
                    base_document_id=document.id,
                    firma_id=document.firma_id,
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
                    base_document_id=document.id,
                    firma_id=document.firma_id,
                    amount=-document.total,
                )
            )

    # Наличные накладные: движение денег по кассе (продажа — приход,
    # покупка — расход). Взаиморасчёты при наличной оплате не возникают.
    if doc_type == DocType.RASHOD and subtype == DocSubtype.CASH:
        session.add(
            MoneyMovement(
                document_id=document.id,
                date=document.date,
                kassa_id=document.kassa_id,
                kontragent_id=document.kontragent_id,
                firma_id=document.firma_id,
                amount=document.total,
            )
        )
    elif doc_type == DocType.PRIHOD and subtype == DocSubtype.CASH:
        session.add(
            MoneyMovement(
                document_id=document.id,
                date=document.date,
                kassa_id=document.kassa_id,
                kontragent_id=document.kontragent_id,
                firma_id=document.firma_id,
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
                firma_id=document.firma_id,
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
                    base_document_id=base_document_id,
                    firma_id=document.firma_id,
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
                firma_id=document.firma_id,
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
                    base_document_id=base_document_id,
                    firma_id=document.firma_id,
                    amount=document.total,
                )
            )
    elif doc_type == DocType.VVOD_OSTATKOV_DENEG:
        session.add(
            MoneyMovement(
                document_id=document.id,
                date=document.date,
                kassa_id=document.kassa_id,
                firma_id=document.firma_id,
                amount=document.total,
            )
        )


async def _outgoing_stock_cost(session: AsyncSession, document_id: int) -> Decimal:
    """Сумма себестоимости списанных (отрицательных) движений документа."""
    result = await session.execute(
        select(func.coalesce(func.sum(StockMovement.amount), 0)).where(
            StockMovement.document_id == document_id,
            StockMovement.quantity < 0,
        )
    )
    return -(result.scalar() or Decimal("0"))


async def _incoming_stock_cost(session: AsyncSession, document_id: int) -> Decimal:
    """Сумма стоимости приходных (положительных) движений документа."""
    result = await session.execute(
        select(func.coalesce(func.sum(StockMovement.amount), 0)).where(
            StockMovement.document_id == document_id,
            StockMovement.quantity > 0,
        )
    )
    return result.scalar() or Decimal("0")


async def _apply_accounting(session: AsyncSession, document: Document, doc_type: DocType) -> None:
    """Формирует автоматические бухгалтерские проводки при проведении."""
    # Сбрасываем накопленные движения в БД, чтобы SELECT ниже (расчёт
    # себестоимости по StockMovement) видел только что созданные строки.
    # При autoflush=False без этого flush сумма списания была бы нулевой.
    await session.flush()

    def entry(debit: str, credit: str, amount: Decimal, *, kontragent_id: int | None = None):
        if amount == 0:
            return
        session.add(
            AccountingEntry(
                document_id=document.id,
                date=document.date,
                account_debit=debit,
                account_credit=credit,
                amount=amount,
                kontragent_id=kontragent_id,
            )
        )

    if doc_type == DocType.PRIHOD:
        # Поступление товаров: Дт 41 «Товары» / Кт 60 «Расчёты с поставщиками».
        entry("41", "60", document.total, kontragent_id=document.kontragent_id)
    elif doc_type == DocType.VOZVRAT:
        # Возврат товара от покупателя: Дт 41 / Кт 62.
        entry("41", "62", document.total, kontragent_id=document.kontragent_id)
    elif doc_type == DocType.RASHOD:
        # Продажа: Дт 62 «Покупатели» / Кт 90.1 «Выручка».
        entry("62", "90.1", document.total, kontragent_id=document.kontragent_id)
        # Себестоимость: Дт 90.2 / Кт 41 (по сумме списанных партий).
        entry("90.2", "41", await _outgoing_stock_cost(session, document.id))
    elif doc_type == DocType.SPISANIE:
        # Списание ТМЦ: Дт 91.2 «Прочие расходы» / Кт 41.
        entry("91.2", "41", await _outgoing_stock_cost(session, document.id))
    elif doc_type == DocType.OPRIHODOVANIE:
        # Оприходование излишков: Дт 41 / Кт 91.1 «Прочие доходы».
        entry("41", "91.1", document.total)
    elif doc_type == DocType.INVENTARIZACIYA:
        # Инвентаризация: излишек → доход, недостача → недостачи.
        entry("41", "91.1", await _incoming_stock_cost(session, document.id))
        entry("94", "41", await _outgoing_stock_cost(session, document.id))
    elif doc_type == DocType.VVOD_OSTATKOV:
        # Ввод начальных остатков ТМЦ: Дт 41 / Кт 00 «Вспомогательный счёт».
        entry("41", "00", document.total)
    elif doc_type == DocType.VVOD_OSTATKOV_DENEG:
        # Ввод начальных остатков денег: Дт 50 / Кт 00.
        entry("50", "00", document.total)
    elif doc_type == DocType.PRIHODNY_KASSOVY_ORDER:
        # Приход наличных: Дт 50 «Касса» / Кт 62 «Покупатели».
        entry("50", "62", document.total, kontragent_id=document.kontragent_id)
    elif doc_type == DocType.RASHODNY_KASSOVY_ORDER:
        # Расход наличных: Дт 62 / Кт 50.
        entry("62", "50", document.total, kontragent_id=document.kontragent_id)
    elif doc_type == DocType.PLATEZHNOE_PORUCHENIE:
        # Безналичный платёж: Дт 60 «Поставщики» / Кт 51 «Расчётный счёт».
        entry("60", "51", document.total, kontragent_id=document.kontragent_id)


async def unpost_document(
    session: AsyncSession, document: Document, user_id: int | None = None
) -> Document:
    """Отменяет проведение: удаляет движения и восстанавливает партии."""
    # Сериализуем с post_document (общий advisory-lock на документ).
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :key)"),
        {"ns": _POST_LOCK_NAMESPACE, "key": document.id},
    )
    status_row = (
        await session.execute(
            select(Document.status).where(Document.id == document.id)
        )
    ).scalar_one_or_none()
    if status_row != DocumentStatus.POSTED:
        return await get_document(session, document.id)

    try:
        doc_type = DocType(document.doc_type)
        if doc_type in _STOCK_DOC_TYPES:
            await _rollback_stock(session, document)
        elif doc_type == DocType.PEREOCENKA:
            await _rollback_revaluation(session, document)

        # Удаляем движения денег и взаиморасчётов.
        await _delete_movements(session, document.id)

        document.status = DocumentStatus.DRAFT
        document.posted_at = None
        _log(session, document, "unpost", user_id=user_id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return await get_document(session, document.id)


async def _delete_movements(session: AsyncSession, document_id: int) -> None:
    for model in (MoneyMovement, SettlementMovement, AccountingEntry):
        result = await session.execute(
            select(model).where(model.document_id == document_id)
        )
        for row in result.scalars():
            await session.delete(row)


async def _rollback_stock(session: AsyncSession, document: Document) -> None:
    """Восстанавливает партии при отмене проведения (обратные движения).

    Движения расхода хранят ``batch_id`` (состав списания по партиям), поэтому
    отмена проведения точно восстанавливает исходные партии без потери
    себестоимости (FIFO/LIFO).
    """
    result = await session.execute(
        select(StockMovement).where(StockMovement.document_id == document.id)
    )
    movements = list(result.scalars())

    batches_to_delete: list[stock_service.StockBatch] = []
    for movement in movements:
        if not movement.batch_id:
            continue
        batch = await session.get(stock_service.StockBatch, movement.batch_id)
        if batch is None:
            continue

        if movement.quantity < 0:
            # Списанная партия — возвращаем количество.
            batch.quantity += -movement.quantity
            if batch.quantity == 0 and batch.source_document_id == document.id:
                # Отрицательная партия, созданная при «Без контроля остатков».
                batches_to_delete.append(batch)
        else:
            # Созданная документом партия (приход/приёмка) — убираем её.
            if batch.quantity < movement.quantity:
                raise DocumentError(
                    "Cannot unpost: stock was already consumed by later documents. "
                    "Unpost dependent documents first."
                )
            batch.quantity -= movement.quantity
            if batch.quantity == 0 and batch.source_document_id == document.id:
                batches_to_delete.append(batch)

    # Сначала удаляем движения (снимаем FK на партии), затем — опустевшие партии.
    for movement in movements:
        await session.delete(movement)
    await session.flush()
    for batch in batches_to_delete:
        await session.delete(batch)


async def mark_for_deletion(
    session: AsyncSession, document: Document, user_id: int | None = None
) -> Document:
    """Помечает документ на удаление (после отмены проведения)."""
    if document.status == DocumentStatus.POSTED:
        await unpost_document(session, document, user_id=user_id)
    document.status = DocumentStatus.MARKED_DELETED
    _log(session, document, "delete", user_id=user_id)
    await session.commit()
    return await get_document(session, document.id)
