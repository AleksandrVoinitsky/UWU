"""Справочники: фирмы, склады, кассы, сотрудники.

См. также: :mod:`app.models.enums`, :mod:`app.models.catalog.valyuty`.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin
from app.models.enums import SkladTip


class Firma(Base, IdMixin, TimestampMixin):
    """Своё юридическое лицо (фирма)."""

    __tablename__ = "firmy"

    name: Mapped[str] = mapped_column(String(40), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(65), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency_buh_id: Mapped[int | None] = mapped_column(ForeignKey("valyuty.id"), nullable=True)
    currency_upr_id: Mapped[int | None] = mapped_column(ForeignKey("valyuty.id"), nullable=True)

    currency_buh: Mapped["Valyuta | None"] = relationship(foreign_keys=[currency_buh_id])  # noqa: F821
    currency_upr: Mapped["Valyuta | None"] = relationship(foreign_keys=[currency_upr_id])  # noqa: F821


class Sklad(Base, IdMixin, TimestampMixin):
    """Склад (оптовый / розничный / НТТ)."""

    __tablename__ = "sklady"

    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    tip: Mapped[SkladTip] = mapped_column(String(20), default=SkladTip.OPTOVY, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Sotrudnik(Base, IdMixin, TimestampMixin):
    """Сотрудник организации."""

    __tablename__ = "sotrudniki"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Kassa(Base, IdMixin, TimestampMixin):
    """Касса (виртуальная). Физическая касса не реализуется — заглушка."""

    __tablename__ = "kassy"

    name: Mapped[str] = mapped_column(String(40), nullable=False)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("valyuty.id"), nullable=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("sotrudniki.id"), nullable=True)

    currency: Mapped["Valyuta | None"] = relationship()  # noqa: F821
    responsible: Mapped[Sotrudnik | None] = relationship()
