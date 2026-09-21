"""Справочник контрагентов с подчинёнными: договоры, расчётные счета.

Иерархический справочник (``parent_id``). Задолженность вычисляется автоматически
по регистрам взаиморасчётов.

См. также: :mod:`app.models.enums`, :mod:`app.models.registry.settlement`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin
from app.models.enums import KontragentVid


class Kontragent(Base, IdMixin, TimestampMixin):
    """Контрагент (покупатель / поставщик)."""

    __tablename__ = "kontragenty"

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("kontragenty.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(9), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(65), nullable=True)
    vid: Mapped[KontragentVid] = mapped_column(String(10), default=KontragentVid.YUR, nullable=False)
    inn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    okpo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actual_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phones: Mapped[str | None] = mapped_column(String(30), nullable=True)

    parent: Mapped["Kontragent | None"] = relationship(remote_side="Kontragent.id")
    dogovory: Mapped[list["Dogovor"]] = relationship(
        back_populates="kontragent", cascade="all, delete-orphan"
    )


class Dogovor(Base, IdMixin, TimestampMixin):
    """Договор — основание взаиморасчётов."""

    __tablename__ = "dogovory"

    kontragent_id: Mapped[int] = mapped_column(ForeignKey("kontragenty.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_term_days: Mapped[int | None] = mapped_column(Numeric(10, 0), nullable=True)

    kontragent: Mapped[Kontragent] = relationship(back_populates="dogovory")


class RaschetnySchet(Base, IdMixin, TimestampMixin):
    """Расчётный (банковский) счёт контрагента."""

    __tablename__ = "raschetnye_scheta"

    kontragent_id: Mapped[int] = mapped_column(ForeignKey("kontragenty.id"), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account: Mapped[str] = mapped_column(String(30), nullable=False)
    bik: Mapped[str | None] = mapped_column(String(12), nullable=True)

    kontragent: Mapped[Kontragent] = relationship()
