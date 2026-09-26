"""Перечисления предметной области (аналог «Перечисление» в 1С 7.7).

Все перечисления хранятся в БД как строки: модели описывают колонки через
``String`` с типом ``Mapped[StrEnum]``. Поскольку :class:`StrEnum` — подкласс
``str``, сравнения ``значение == Перечисление.X`` работают и при чтении строки
из БД. Такой подход проще миграций и совместимости с PostgreSQL.

См. также: :mod:`app.models.catalog`, :mod:`app.models.document`.
"""
from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    """Строковое перечисление; ``str(value)`` возвращает значение без префикса."""

    def __str__(self) -> str:  # pragma: no cover - вспомогательный
        return self.value


class NomenklaturaVid(StrEnum):
    """Вид номенклатуры (Товар / Материал / Продукция / Тара / Услуга)."""

    TOVAR = "tovar"
    MATERIAL = "material"
    PRODUKCIYA = "produkciya"
    TARA = "tara"
    USLUGA = "usluga"


class KontragentVid(StrEnum):
    """Вид контрагента (юридическое / физическое лицо)."""

    YUR = "yur"
    FIZ = "fiz"


class SkladTip(StrEnum):
    """Тип склада."""

    OPTOVY = "optovy"
    ROZNICHNY = "roznichny"
    NEAVTOMAT = "neavtomat"


class DocumentStatus(StrEnum):
    """Статус документа (проведение / удаление)."""

    DRAFT = "draft"                 # Непроведённый
    POSTED = "posted"               # Проведённый
    MARKED_DELETED = "deleted"      # Помечен на удаление


class DocumentDirection(StrEnum):
    """Направление движения товара по документу."""

    IN = "in"
    OUT = "out"


class CostMethod(StrEnum):
    """Метод списания себестоимости партий."""

    FIFO = "fifo"
    LIFO = "lifo"
    AVERAGE = "average"


class RestockControl(StrEnum):
    """Режим контроля остатков."""

    BY_FIRM = "by_firm"
    BY_WAREHOUSE = "by_warehouse"
    NONE = "none"


class PaymentKind(StrEnum):
    """Вид денежной операции."""

    IN = "in"
    OUT = "out"


class ZakazState(StrEnum):
    """Состояние заявки покупателя."""

    NEW = "new"
    IN_WORK = "in_work"
    DONE = "done"
    CANCELLED = "cancelled"


class RoleKey(StrEnum):
    """Встроенные роли системы."""

    ADMIN = "admin"
    OPERATOR = "operator"   # оператор (торговый учёт)
    ACCOUNTANT = "accountant"  # бухгалтер


class DocType(StrEnum):
    """Виды документов."""

    PRIHOD = "prihod"                    # Приходная накладная (за наличный/кредит/на реализацию)
    RASHOD = "rashod"                    # Расходная накладная
    PEREMESHENIE = "peremeshenie"        # Перемещение
    SPISANIE = "spisanie"                # Списание
    OPRIHODOVANIE = "oprihodovanie"      # Оприходование излишков
    INVENTARIZACIYA = "inventarizaciya"  # Инвентаризация
    PEREOCENKA = "pereocenka"            # Переоценка
    VVOD_OSTATKOV = "vvod_ostatkov"      # Ввод остатков ТМЦ
    PLATEZHNOE_PORUCHENIE = "platezhnoe_poruchenie"  # Платёжное поручение
    PRIHODNY_KASSOVY_ORDER = "pko"       # Приходный кассовый ордер
    RASHODNY_KASSOVY_ORDER = "rko"       # Расходный кассовый ордер
    VVOD_OSTATKOV_DENEG = "vvod_ostatkov_deneg"  # Ввод остатков денег
    ZAKAZ = "zakaz"                              # Заявка покупателя
    VOZVRAT = "vozvrat"                          # Возврат товара от покупателя


class DocSubtype(StrEnum):
    """Подвиды накладных (способ расчёта)."""

    CASH = "cash"
    CREDIT = "credit"
    REALIZATION = "realization"
