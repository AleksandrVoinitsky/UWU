"""Модели покупателей и корзины (клиентский сайт/каталог).

Учётные записи покупателей полностью отделены от сотрудников (:class:`User`):
другая таблица, отдельные токены. Логин покупателя — номер телефона.

См. также: :mod:`app.models.users`, :mod:`app.services.customer_service`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class Customer(Base, IdMixin, TimestampMixin):
    """Учётная запись покупателя (логин — номер телефона)."""

    __tablename__ = "customers"

    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cart: Mapped["Cart | None"] = relationship(
        back_populates="customer", cascade="all, delete-orphan", uselist=False
    )


class Cart(Base, IdMixin, TimestampMixin):
    """Корзина покупателя (одна на покупателя)."""

    __tablename__ = "carts"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), unique=True, nullable=False, index=True
    )

    customer: Mapped[Customer] = relationship(back_populates="cart")
    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.id"
    )


class CartItem(Base, IdMixin):
    """Позиция корзины."""

    __tablename__ = "cart_items"

    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"), nullable=False, index=True)
    nomenklatura_id: Mapped[int] = mapped_column(ForeignKey("nomenklatura.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="items")
    nomenklatura: Mapped["Nomenklatura"] = relationship()  # noqa: F821
