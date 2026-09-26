"""Регрессионные тесты на исправления из docs/AUDIT.md.

Каждый тест закрепляет конкретную исправленную уязвимость/баг, чтобы она не
вернулась. Покрывает: XSS (C1), race-условие/отрицательный остаток (C2/H8),
двойное проведение (C3), себестоимость продажи (C4), права доступа (H1/H2),
rate limiting (H3), fail-fast секретов (H4), CSRF (H5), денежные движения
наличных (H9), отмену проведения FIFO (H10), аудит (M14), last_login (M18),
кассовые смены (M21).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.ratelimit import SlidingWindowRateLimiter
from app.core.security import create_access_token, validate_security_settings
from app.models.catalog import Kassa, Kontragent, Nomenklatura, Sklad
from app.models.enums import DocSubtype, DocType
from app.models.registry import AccountingEntry, AuditLog, MoneyMovement, StockBatch
from app.models.users import Role
from app.services import (
    cash_service,
    catalog_service,
    document_service,
    stock_service,
    user_service,
)
from app.web.trade import _json_safe


# --- Хелперы ---


async def _make_item(seeded_session, code="001", name="Товар") -> Nomenklatura:
    return await catalog_service.create_one(
        seeded_session, Nomenklatura, code=code, name=name, vid="tovar"
    )


async def _make_sklad(seeded_session, code="001", name="Склад") -> Sklad:
    return await catalog_service.create_one(
        seeded_session, Sklad, code=code, name=name, tip="optovy"
    )


async def _prihod(seeded_session, item, sklad, qty, price) -> document_service.Document:
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": qty, "price": price}],
    )
    return await document_service.post_document(seeded_session, doc)


async def _operator_role_id(seeded_session) -> int:
    role = (
        await seeded_session.execute(select(Role).where(Role.key == "operator"))
    ).scalar_one()
    return role.id


# --- C1: XSS ---


def test_json_safe_escapes_script_breakout():
    payload = [{"name": "</script><script>alert(1)</script>"}]
    out = _json_safe(payload)
    assert "<" not in out
    assert "</script>" not in out
    assert "\\u003c" in out


# --- C2/H8: контроль остатков ---


async def test_none_restock_control_allows_negative(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    await catalog_service.set_constant(seeded_session, "restock_control", "none")

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, rashod)

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("-5")


async def test_warehouse_restock_control_rejects(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    await catalog_service.set_constant(seeded_session, "restock_control", "by_warehouse")

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("100")}],
    )
    with pytest.raises(stock_service.InsufficientStockError):
        await document_service.post_document(seeded_session, rashod)


# --- C3: двойное проведение ---


async def test_post_is_idempotent(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("100")}],
    )
    await document_service.post_document(seeded_session, doc)
    await document_service.post_document(seeded_session, doc)

    assert await stock_service.get_balance(seeded_session, item.id, sklad.id) == Decimal("5")
    batches = (
        await seeded_session.execute(
            select(StockBatch).where(StockBatch.nomenklatura_id == item.id)
        )
    ).scalars().all()
    assert len(batches) == 1


# --- C4: себестоимость продажи в проводках ---


async def test_rashod_generates_cost_accounting_entry(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("3"), "price": Decimal("300")}],
    )
    await document_service.post_document(seeded_session, rashod)

    entries = (
        await seeded_session.execute(
            select(AccountingEntry).where(AccountingEntry.document_id == rashod.id)
        )
    ).scalars().all()
    cost = [e for e in entries if e.account_debit == "90.2" and e.account_credit == "41"]
    assert len(cost) == 1
    assert cost[0].amount == Decimal("300.00")  # 3 × 100 (FIFO себестоимость)


# --- H9: денежные движения наличных накладных ---


async def test_cash_sale_creates_money_movement(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    kontragent = await catalog_service.create_one(
        seeded_session, Kontragent, code="001", name="Покупатель"
    )
    kassa = await catalog_service.create_one(seeded_session, Kassa, name="Касса 1")
    await _prihod(seeded_session, item, sklad, Decimal("10"), Decimal("100"))

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        subtype=DocSubtype.CASH,
        doc_date=date(2025, 1, 2),
        sklad_id=sklad.id,
        kontragent_id=kontragent.id,
        kassa_id=kassa.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("2"), "price": Decimal("150")}],
    )
    await document_service.post_document(seeded_session, rashod)

    money = (
        await seeded_session.execute(
            select(MoneyMovement).where(MoneyMovement.document_id == rashod.id)
        )
    ).scalars().all()
    assert len(money) == 1
    assert money[0].amount == Decimal("300.00")  # 2 × 150 — приход в кассу


# --- H10: отмена проведения восстанавливает FIFO-партии ---


async def test_unpost_restores_fifo_batches(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("100"))
    await _prihod(seeded_session, item, sklad, Decimal("5"), Decimal("200"))

    rashod = await document_service.create_document(
        seeded_session,
        doc_type=DocType.RASHOD,
        doc_date=date(2025, 1, 3),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("5"), "price": Decimal("300")}],
    )
    await document_service.post_document(seeded_session, rashod)
    await document_service.unpost_document(seeded_session, rashod)

    batches = (
        await seeded_session.execute(
            select(StockBatch)
            .where(StockBatch.nomenklatura_id == item.id)
            .order_by(StockBatch.id)
        )
    ).scalars().all()
    assert len(batches) == 2
    assert batches[0].quantity == Decimal("5")
    assert batches[0].unit_cost == Decimal("100")
    assert batches[1].quantity == Decimal("5")
    assert batches[1].unit_cost == Decimal("200")


# --- H1/H2: права доступа ---


async def test_web_read_requires_permission(client, seeded_session):
    user = await user_service.create_user(seeded_session, login="no_perm", password="secret123")
    client.cookies.set("access_token", create_access_token(str(user.id)))
    resp = await client.get("/catalog/nomenklatura")
    assert resp.status_code == 403


async def test_api_documents_read_requires_permission(client, seeded_session):
    user = await user_service.create_user(seeded_session, login="no_perm2", password="secret123")
    token = create_access_token(str(user.id))
    resp = await client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# --- H3: rate limiting ---


def test_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.hit("k") is True
    assert limiter.hit("k") is True
    assert limiter.hit("k") is True
    assert limiter.hit("k") is False


async def test_login_rate_limited(client):
    for _ in range(10):
        resp = await client.post(
            "/api/auth/login", json={"login": "ratelimit_probe", "password": "x"}
        )
        assert resp.status_code == 401
    resp = await client.post(
        "/api/auth/login", json={"login": "ratelimit_probe", "password": "x"}
    )
    assert resp.status_code == 429


# --- H4: fail-fast секретов в проде ---


def test_security_fail_fast_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "short")
    with pytest.raises(RuntimeError):
        validate_security_settings()


# --- H5: CSRF ---


async def test_csrf_blocks_cross_origin_post(client, admin_token):
    client.cookies.set("access_token", admin_token)
    resp = await client.post(
        "/rmk/shift/open",
        data={"kassa_id": "", "opening_amount": "0"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


# --- M14: аудит записывает действующего пользователя ---


async def test_audit_log_records_acting_user(seeded_session):
    item = await _make_item(seeded_session)
    sklad = await _make_sklad(seeded_session)
    operator = await user_service.create_user(
        seeded_session, login="audit_op", password="secret123",
        role_id=await _operator_role_id(seeded_session),
    )
    doc = await document_service.create_document(
        seeded_session,
        doc_type=DocType.PRIHOD,
        doc_date=date(2025, 1, 1),
        sklad_id=sklad.id,
        items=[{"nomenklatura_id": item.id, "quantity": Decimal("1"), "price": Decimal("10")}],
        created_by_id=operator.id,
    )
    await document_service.post_document(seeded_session, doc, user_id=operator.id)

    logs = (
        await seeded_session.execute(
            select(AuditLog).where(AuditLog.entity_type == "document")
        )
    ).scalars().all()
    assert any(l.action == "post" and l.user_id == operator.id for l in logs)


# --- M18: last_login_at заполняется ---


async def test_last_login_at_set_on_auth(seeded_session):
    from app.services.auth_service import authenticate

    user = await user_service.create_user(seeded_session, login="login_user", password="secret123")
    assert user.last_login_at is None
    token = await authenticate(seeded_session, "login_user", "secret123")
    assert token
    await seeded_session.refresh(user)
    assert user.last_login_at is not None


# --- M21: вторая открытая смена не создаётся ---


async def test_open_shift_is_single_per_kassa(seeded_session):
    kassa = await catalog_service.create_one(seeded_session, Kassa, name="Касса")
    shift1 = await cash_service.open_shift(
        seeded_session, kassa_id=kassa.id, opening_amount=Decimal("0"), user_id=None
    )
    shift2 = await cash_service.open_shift(
        seeded_session, kassa_id=kassa.id, opening_amount=Decimal("100"), user_id=None
    )
    assert shift1.id == shift2.id
