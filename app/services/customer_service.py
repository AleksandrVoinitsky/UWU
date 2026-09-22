"""Сервис покупателей: регистрация, аутентификация, корзина, заказы.

Логика клиентского сайта/каталога. Покупатель подтверждает корзину — создаётся
документ «Заявка покупателя» (``ZAKAZ``), который оператор далее ведёт обычным
циклом (резерв → отгрузка). Контрагент определяется по номеру телефона.

См. также: :mod:`app.models.customer`, :mod:`app.models.catalog`,
:mod:`app.services.document_service`, :mod:`app.core.security`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.catalog import Category, Kontragent, Nomenklatura
from app.models.customer import Cart, CartItem, Customer
from app.models.document.base_document import Document
from app.models.enums import DocType
from app.models.registry import StockBatch
from app.services import document_service

logger = get_logger("app.customer")


class CustomerError(Exception):
    """Ошибка клиентского сервиса (валидация и т.п.)."""


class CustomerAuthError(CustomerError):
    """Неверный телефон/пароль или неактивный аккаунт."""


# --- Регистрация и аутентификация ---


async def get_customer_by_phone(session: AsyncSession, phone: str) -> Customer | None:
    stmt = select(Customer).where(Customer.phone == phone)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_customer(session: AsyncSession, customer_id: int) -> Customer | None:
    return await session.get(Customer, customer_id)


async def register(
    session: AsyncSession, phone: str, password: str, name: str | None = None
) -> Customer:
    """Регистрирует покупателя по телефону и паролю."""
    phone = (phone or "").strip()
    if not phone:
        raise CustomerError("Укажите номер телефона")
    if not password or len(password) < 6:
        raise CustomerError("Пароль должен быть не короче 6 символов")
    if await get_customer_by_phone(session, phone) is not None:
        raise CustomerError("Покупатель с таким телефоном уже зарегистрирован")
    customer = Customer(
        phone=phone,
        password_hash=hash_password(password),
        name=name or None,
    )
    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    logger.info("Зарегистрирован покупатель %s", phone)
    return customer


async def authenticate(session: AsyncSession, phone: str, password: str) -> Customer:
    """Аутентифицирует покупателя по телефону и паролю."""
    customer = await get_customer_by_phone(session, phone)
    if customer is None or not verify_password(password, customer.password_hash):
        raise CustomerAuthError("Неверный телефон или пароль")
    if not customer.is_active:
        raise CustomerAuthError("Аккаунт отключён")
    return customer


async def list_customers(session: AsyncSession) -> list[Customer]:
    result = await session.execute(select(Customer).order_by(Customer.id.desc()))
    return list(result.scalars())


async def delete_customer(session: AsyncSession, customer: Customer) -> None:
    await session.delete(customer)
    await session.commit()


# --- Категории ---


async def list_categories(session: AsyncSession) -> list[Category]:
    result = await session.execute(
        select(Category).order_by(Category.sort, Category.id)
    )
    return list(result.scalars())


# --- Каталог (товары в наличии) ---


async def available_products(
    session: AsyncSession,
    category_id: int | None = None,
    search: str | None = None,
) -> list[dict]:
    """Товары, доступные к заказу (есть остаток на складах)."""
    stock_map: dict[int, Decimal] = {
        nid: qty
        for nid, qty in (
            await session.execute(
                select(StockBatch.nomenklatura_id, func.sum(StockBatch.quantity))
                .group_by(StockBatch.nomenklatura_id)
                .having(func.sum(StockBatch.quantity) > 0)
            )
        ).all()
    }

    stmt = select(Nomenklatura).order_by(Nomenklatura.name)
    if category_id is not None:
        stmt = stmt.where(Nomenklatura.category_id == category_id)
    if search:
        stmt = stmt.where(Nomenklatura.name.ilike(f"%{search}%"))
    result = await session.execute(stmt)

    products: list[dict] = []
    for p in result.scalars():
        stock = stock_map.get(p.id, Decimal("0"))
        if stock <= 0:
            continue
        products.append(
            {
                "id": p.id,
                "name": p.name,
                "full_name": p.full_name,
                "artikul": p.artikul,
                "image_path": p.image_path,
                "category_id": p.category_id,
                "price": p.retail_price or Decimal("0"),
                "stock": stock,
            }
        )
    return products


# --- Корзина ---


async def get_cart(session: AsyncSession, customer_id: int) -> Cart:
    """Возвращает корзину покупателя (создаёт при отсутствии)."""
    stmt = select(Cart).where(Cart.customer_id == customer_id)
    cart = (await session.execute(stmt)).scalar_one_or_none()
    if cart is None:
        cart = Cart(customer_id=customer_id)
        session.add(cart)
        await session.flush()
    return cart


async def get_cart_items(session: AsyncSession, customer_id: int) -> list[dict]:
    """Позиции корзины с данными товара и суммой."""
    cart = await get_cart(session, customer_id)
    result = await session.execute(
        select(CartItem, Nomenklatura)
        .join(Nomenklatura, Nomenklatura.id == CartItem.nomenklatura_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.id)
    )
    items: list[dict] = []
    for ci, n in result.all():
        price = n.retail_price or Decimal("0")
        items.append(
            {
                "id": ci.id,
                "nomenklatura_id": n.id,
                "name": n.name,
                "image_path": n.image_path,
                "quantity": ci.quantity,
                "price": price,
                "amount": (ci.quantity * price).quantize(Decimal("0.01")),
            }
        )
    return items


async def cart_total(session: AsyncSession, customer_id: int) -> Decimal:
    items = await get_cart_items(session, customer_id)
    return sum((i["amount"] for i in items), Decimal("0")).quantize(Decimal("0.01"))


async def add_to_cart(
    session: AsyncSession, customer_id: int, nomenklatura_id: int, quantity: Decimal
) -> None:
    """Добавляет (или увеличивает) позицию в корзине."""
    if quantity <= 0:
        raise CustomerError("Количество должно быть положительным")
    cart = await get_cart(session, customer_id)
    stmt = select(CartItem).where(
        CartItem.cart_id == cart.id, CartItem.nomenklatura_id == nomenklatura_id
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        session.add(
            CartItem(cart_id=cart.id, nomenklatura_id=nomenklatura_id, quantity=quantity)
        )
    else:
        item.quantity = item.quantity + quantity
    await session.commit()


async def set_cart_quantity(
    session: AsyncSession, customer_id: int, item_id: int, quantity: Decimal
) -> None:
    """Устанавливает количество позиции (0 — удалить)."""
    cart = await get_cart(session, customer_id)
    stmt = select(CartItem).where(CartItem.cart_id == cart.id, CartItem.id == item_id)
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise CustomerError("Позиция не найдена")
    if quantity <= 0:
        await session.delete(item)
    else:
        item.quantity = quantity
    await session.commit()


async def clear_cart(session: AsyncSession, customer_id: int) -> None:
    cart = await get_cart(session, customer_id)
    cart_items = (
        await session.execute(select(CartItem).where(CartItem.cart_id == cart.id))
    ).scalars().all()
    for item in cart_items:
        await session.delete(item)
    await session.commit()


# --- Заказы ---


async def match_kontragent_by_phone(
    session: AsyncSession, phone: str | None
) -> Kontragent | None:
    """Ищет контрагента по номеру телефона (точное совпадение, затем подстрока)."""
    if not phone:
        return None
    stmt = select(Kontragent).where(Kontragent.phones == phone)
    kg = (await session.execute(stmt)).scalar_one_or_none()
    if kg is None:
        kg = (
            await session.execute(
                select(Kontragent).where(Kontragent.phones.ilike(f"%{phone}%"))
            )
        ).scalars().first()
    return kg


async def checkout(session: AsyncSession, customer: Customer) -> Document:
    """Подтверждает корзину: создаёт заявку покупателя (ZAKAZ) и очищает корзину."""
    items = await get_cart_items(session, customer.id)
    if not items:
        raise CustomerError("Корзина пуста")

    kontragent = await match_kontragent_by_phone(session, customer.phone)

    doc_items = [
        {
            "nomenklatura_id": i["nomenklatura_id"],
            "quantity": i["quantity"],
            "price": i["price"],
        }
        for i in items
    ]

    # Очищаем корзину перед созданием документа (коммитится вместе с ним).
    cart = await get_cart(session, customer.id)
    cart_items = (
        await session.execute(select(CartItem).where(CartItem.cart_id == cart.id))
    ).scalars().all()
    for ci in cart_items:
        await session.delete(ci)

    doc = await document_service.create_document(
        session,
        doc_type=DocType.ZAKAZ,
        doc_date=date.today(),
        kontragent_id=kontragent.id if kontragent else None,
        extra={
            "state": "new",
            "source": "customer",
            "customer_id": customer.id,
            "customer_phone": customer.phone,
            "customer_name": customer.name,
        },
        items=doc_items,
        created_by_id=None,
    )
    logger.info(
        "Заказ покупателя #%s создан (%s, %d позиций)",
        doc.number,
        customer.phone,
        len(doc_items),
    )
    return doc


async def get_customer_order(
    session: AsyncSession, customer_id: int, document_id: int
) -> Document | None:
    """Заявка покупателя, принадлежащая покупателю (с загруженными строками)."""
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.items))
        .where(Document.id == document_id, Document.doc_type == DocType.ZAKAZ.value)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        return None
    extra = doc.extra or {}
    if extra.get("customer_id") != customer_id:
        return None
    return doc


async def list_customer_orders(
    session: AsyncSession, customer_id: int
) -> list[Document]:
    """Все заявки покупателя."""
    result = await session.execute(
        select(Document)
        .where(Document.doc_type == DocType.ZAKAZ.value)
        .order_by(Document.date.desc(), Document.id.desc())
    )
    docs = []
    for doc in result.scalars():
        if (doc.extra or {}).get("customer_id") == customer_id:
            docs.append(doc)
    return docs


async def order_context(session: AsyncSession, doc: Document) -> dict:
    """Контекст заказа (для отображения и PDF): позиции с названиями и итог."""
    items = []
    for it in doc.items:
        nomen = await session.get(Nomenklatura, it.nomenklatura_id)
        items.append(
            {
                "name": nomen.name if nomen else f"#{it.nomenklatura_id}",
                "quantity": it.quantity,
                "price": it.price,
                "amount": it.amount,
            }
        )
    extra = doc.extra or {}
    return {
        "id": doc.id,
        "number": doc.number,
        "date": doc.date.isoformat(),
        "total": doc.total,
        "status": extra.get("state"),
        "customer_name": extra.get("customer_name"),
        "customer_phone": extra.get("customer_phone"),
        "items": items,
    }
