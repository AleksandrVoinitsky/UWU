"""Тесты сервисов справочников (НСИ) и ценообразования.

Покрывают ``app.services.catalog_service`` (генерация кодов, константы, курсы
валют) и ``app.services.price_service`` (автонаценка, итоговая цена, явные цены).

См. также: :mod:`app.services.catalog_service`, :mod:`app.services.price_service`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.catalog import Kontragent, Nomenklatura, TipTsen, Valyuta
from app.models.constants import DEFAULT_CONSTANTS
from app.services import catalog_service, price_service


# ---------------------------------------------------------------------------
# catalog_service: генерация кодов
# ---------------------------------------------------------------------------


async def test_next_code_empty(session):
    """Без кодов генерируется первый код «001»."""
    assert await catalog_service.next_code(session, Nomenklatura) == "001"
    # next_code берёт transaction-scoped advisory lock; завершаем транзакцию,
    # чтобы замок не утекал в следующий тест.
    await session.commit()


async def test_next_code_increments_numerically(session):
    """Коды инкрементируются по числовому значению (001, 002, ...)."""
    session.add_all(
        [
            Nomenklatura(code="001", name="Товар 1"),
            Nomenklatura(code="002", name="Товар 2"),
        ]
    )
    await session.commit()
    assert await catalog_service.next_code(session, Nomenklatura) == "003"
    await session.commit()


async def test_next_code_ignores_non_numeric_and_empty(session):
    """Нечисловые («ABC») и пустые коды не влияют на вычисление максимума."""
    session.add_all(
        [
            Nomenklatura(code="001", name="Числовой"),
            Nomenklatura(code="ABC", name="Буквенный"),
            Nomenklatura(code="", name="Пустой"),
        ]
    )
    await session.commit()
    # Числовой максимум = 1 → следующий код «002».
    assert await catalog_service.next_code(session, Nomenklatura) == "002"
    await session.commit()


async def test_next_nomenklatura_and_kontragent_codes(session):
    """Последовательная генерация кодов номенклатуры и контрагентов."""
    assert await catalog_service.next_nomenklatura_code(session) == "001"
    assert await catalog_service.next_kontragent_code(session) == "001"

    session.add_all(
        [
            Nomenklatura(code="001", name="Товар"),
            Kontragent(code="001", name="Клиент"),
        ]
    )
    await session.commit()

    assert await catalog_service.next_nomenklatura_code(session) == "002"
    assert await catalog_service.next_kontragent_code(session) == "002"
    await session.commit()


# ---------------------------------------------------------------------------
# catalog_service: курсы валют
# ---------------------------------------------------------------------------


async def test_set_rate_and_get_latest_rate(session):
    """Курс — периодический: возвращается последний курс на/до даты."""
    cur = Valyuta(code="USD", name="Доллар США")
    session.add(cur)
    await session.commit()

    await catalog_service.set_rate(session, cur.id, date(2025, 1, 1), Decimal("90.0000"))
    await catalog_service.set_rate(session, cur.id, date(2025, 1, 10), Decimal("95.0000"))
    await catalog_service.set_rate(session, cur.id, date(2025, 2, 1), Decimal("100.0000"))

    # Точная дата.
    assert (
        await catalog_service.get_latest_rate(session, cur.id, date(2025, 1, 1))
        == Decimal("90.0000")
    )

    # Более ранний курс возвращается при запросе более поздней даты.
    assert (
        await catalog_service.get_latest_rate(session, cur.id, date(2025, 1, 5))
        == Decimal("90.0000")
    )
    assert (
        await catalog_service.get_latest_rate(session, cur.id, date(2025, 1, 15))
        == Decimal("95.0000")
    )

    # Будущий курс НЕ возвращается для более ранней даты.
    assert (
        await catalog_service.get_latest_rate(session, cur.id, date(2025, 1, 20))
        == Decimal("95.0000")
    )
    assert (
        await catalog_service.get_latest_rate(session, cur.id, date(2025, 2, 1))
        == Decimal("100.0000")
    )

    # Нет курса на/до даты.
    assert await catalog_service.get_latest_rate(session, cur.id, date(2024, 12, 31)) is None

    # Повторная установка курса на ту же дату обновляет (а не дублирует) запись.
    await catalog_service.set_rate(session, cur.id, date(2025, 1, 1), Decimal("91.0000"))
    assert (
        await catalog_service.get_latest_rate(session, cur.id, date(2025, 1, 1))
        == Decimal("91.0000")
    )


# ---------------------------------------------------------------------------
# catalog_service: константы
# ---------------------------------------------------------------------------


async def test_constants_set_and_get(session):
    """Установка и чтение константы; значения по умолчанию подмешиваются."""
    defaults = await catalog_service.get_constants(session)
    assert defaults == DEFAULT_CONSTANTS
    assert defaults["restock_control"] == "by_warehouse"

    await catalog_service.set_constant(session, "show_artikul", True)
    await catalog_service.set_constant(session, "custom_key", "hello")

    consts = await catalog_service.get_constants(session)
    assert consts["show_artikul"] is True
    assert consts["custom_key"] == "hello"

    # Значения по умолчанию сохраняются рядом с заданными.
    assert consts["restock_control"] == "by_warehouse"
    assert consts["cost_method"] == "fifo"


# ---------------------------------------------------------------------------
# price_service: автонаценка и итоговая цена
# ---------------------------------------------------------------------------


async def test_auto_price_markup_and_rounding():
    """Автонаценка = закупочная × (1 + наценка/100), округление до 0.01."""
    assert price_service.auto_price(Decimal("100"), Decimal("20")) == Decimal("120.00")
    # Округление до копеек.
    assert price_service.auto_price(Decimal("9.99"), Decimal("10")) == Decimal("10.99")
    # Нулевая/отсутствующая наценка → цена без изменений.
    assert price_service.auto_price(Decimal("100"), None) == Decimal("100.00")
    assert price_service.auto_price(Decimal("100"), Decimal("0")) == Decimal("100.00")
    # Нет закупочной цены → нет автоцены.
    assert price_service.auto_price(None, Decimal("20")) is None


def _nomen(**fields) -> Nomenklatura:
    defaults = dict(code="000", name="Товар", price_mode="free")
    defaults.update(fields)
    return Nomenklatura(**defaults)


async def test_effective_price_by_type():
    """Режим «по виду цен» — автонаценка от закупочной по выбранному виду."""
    tip = TipTsen(name="Опт", markup_percent=Decimal("20"))
    nomen = _nomen(
        code="001",
        name="Товар",
        price_mode="by_type",
        tip_tsen_id=99,
        purchase_price=Decimal("100"),
    )
    assert price_service.effective_price(nomen, {99: tip}) == Decimal("120.00")


async def test_effective_price_free_mode():
    """Режим «свободная цена» — возвращается розничная цена."""
    tip = TipTsen(name="Опт", markup_percent=Decimal("20"))
    nomen = _nomen(
        code="002",
        name="Товар",
        price_mode="free",
        retail_price=Decimal("199"),
    )
    assert price_service.effective_price(nomen, {1: tip}) == Decimal("199.00")


async def test_effective_price_by_type_without_tip():
    """«по виду цен» без выбранного вида цен → свободная розничная цена."""
    nomen = _nomen(
        code="003",
        name="Товар",
        price_mode="by_type",
        tip_tsen_id=None,
        retail_price=Decimal("150"),
    )
    assert price_service.effective_price(nomen, {}) == Decimal("150.00")


# ---------------------------------------------------------------------------
# price_service: разрешение и явные цены
# ---------------------------------------------------------------------------


async def test_resolve_prices_explicit_wins_over_auto(session):
    """Явная цена перекрывает автонаценку; иначе — автонаценка по виду цен."""
    nomen = Nomenklatura(code="001", name="Товар", purchase_price=Decimal("100"))
    tip1 = TipTsen(name="Опт", markup_percent=Decimal("20"))
    tip2 = TipTsen(name="Розница", markup_percent=Decimal("10"))
    session.add_all([nomen, tip1, tip2])
    await session.commit()

    resolved = await price_service.resolve_prices(session, nomen, [tip1, tip2])
    assert resolved[tip1.id] == Decimal("120.00")
    assert resolved[tip2.id] == Decimal("110.00")

    # Явная цена только для tip1 — tip2 остаётся на автонаценке.
    await price_service.set_explicit_price(session, nomen.id, tip1.id, Decimal("150"))
    resolved = await price_service.resolve_prices(session, nomen, [tip1, tip2])
    assert resolved[tip1.id] == Decimal("150.00")
    assert resolved[tip2.id] == Decimal("110.00")


async def test_explicit_price_roundtrip_and_clear(session):
    """Установка/чтение явной цены и её очистка (возврат к автонаценке)."""
    nomen = Nomenklatura(code="001", name="Товар", purchase_price=Decimal("100"))
    tip = TipTsen(name="Опт", markup_percent=Decimal("20"))
    session.add_all([nomen, tip])
    await session.commit()

    assert await price_service.get_explicit_prices(session, nomen.id) == {}

    await price_service.set_explicit_price(session, nomen.id, tip.id, Decimal("150"))
    assert await price_service.get_explicit_prices(session, nomen.id) == {
        tip.id: Decimal("150.00")
    }

    # Перезапись существующей явной цены.
    await price_service.set_explicit_price(session, nomen.id, tip.id, Decimal("160"))
    assert await price_service.get_explicit_prices(session, nomen.id) == {
        tip.id: Decimal("160.00")
    }

    # Очистка удаляет явную цену → возврат к автонаценке.
    await price_service.clear_explicit_price(session, nomen.id, tip.id)
    assert await price_service.get_explicit_prices(session, nomen.id) == {}
    resolved = await price_service.resolve_prices(session, nomen, [tip])
    assert resolved[tip.id] == Decimal("120.00")
