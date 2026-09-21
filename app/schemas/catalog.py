"""Схемы справочников.

См. также: :mod:`app.models.catalog`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValyutaBase(BaseModel):
    code: str = Field(min_length=1, max_length=3)
    name: str = Field(min_length=1, max_length=20)


class ValyutaCreate(ValyutaBase):
    pass


class ValyutaOut(ValyutaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CurrencyRateCreate(BaseModel):
    currency_id: int
    on_date: date
    rate: Decimal
    multiplicity: int = 1


class StavkaNDSBase(BaseModel):
    name: str
    rate: Decimal


class StavkaNDSOut(StavkaNDSBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class EdinitsaBase(BaseModel):
    name: str
    short_name: str
    coefficient: Decimal = Decimal("1")


class EdinitsaOut(EdinitsaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class FirmaBase(BaseModel):
    name: str
    full_name: str | None = None
    inn: str | None = None
    legal_address: str | None = None
    currency_buh_id: int | None = None
    currency_upr_id: int | None = None


class FirmaOut(FirmaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SkladBase(BaseModel):
    code: str = Field(min_length=1, max_length=3)
    name: str
    tip: str = "optovy"
    is_default: bool = False


class SkladOut(SkladBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class KassaBase(BaseModel):
    name: str
    currency_id: int | None = None
    responsible_id: int | None = None


class KassaOut(KassaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SotrudnikBase(BaseModel):
    name: str
    position: str | None = None


class SotrudnikOut(SotrudnikBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class KontragentBase(BaseModel):
    parent_id: int | None = None
    code: str
    name: str
    full_name: str | None = None
    vid: str = "yur"
    inn: str | None = None
    okpo: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    phones: str | None = None


class KontragentOut(KontragentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DogovorBase(BaseModel):
    kontragent_id: int
    name: str
    number: str | None = None
    payment_term_days: int | None = None


class DogovorOut(DogovorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class NomenklaturaBase(BaseModel):
    parent_id: int | None = None
    code: str
    name: str
    full_name: str | None = None
    vid: str = "tovar"
    artikul: str | None = None
    base_unit_id: int | None = None
    main_unit_id: int | None = None
    weight: Decimal | None = None
    is_weighted: bool = False
    barcode: str | None = None
    nds_rate_id: int | None = None
    purchase_price: Decimal | None = None
    retail_price: Decimal | None = None
    price_mode: str = "free"
    tip_tsen_id: int | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class NomenklaturaOut(NomenklaturaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TipTsenBase(BaseModel):
    name: str
    currency_id: int | None = None
    includes_nds: bool = True
    markup_percent: Decimal | None = None


class TipTsenOut(TipTsenBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
