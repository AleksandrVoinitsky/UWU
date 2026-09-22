"""Модели справочников (НСИ)."""
from app.models.catalog.category import Category
from app.models.catalog.firmy import Firma, Kassa, Sklad, Sotrudnik
from app.models.catalog.kontragenty import Dogovor, Kontragent, RaschetnySchet
from app.models.catalog.nomenklatura import Nomenklatura, TipTsen, TsenaNomenklatury
from app.models.catalog.valyuty import (
    CurrencyRate,
    Edinitsa,
    StavkaNDS,
    Valyuta,
)

__all__ = [
    "Category",
    "Firma",
    "Kassa",
    "Sklad",
    "Sotrudnik",
    "Dogovor",
    "Kontragent",
    "RaschetnySchet",
    "Nomenklatura",
    "TipTsen",
    "TsenaNomenklatury",
    "CurrencyRate",
    "Edinitsa",
    "StavkaNDS",
    "Valyuta",
]
