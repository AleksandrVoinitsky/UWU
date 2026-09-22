"""Тесты аутентификации и прав доступа REST API.

Проверяют, что справочники и отчёты не отдаются без аутентификации (регрессия
на уязвимость «открытый API»), а авторизованный администратор работает штатно.

См. также: :mod:`app.api.catalog`, :mod:`app.api.reports`,
:mod:`app.core.deps`.
"""
from __future__ import annotations


# --- Каталог: чтение ---


async def test_catalog_read_requires_auth(client):
    for path in (
        "/api/catalog/valyuty",
        "/api/catalog/stavki_nds",
        "/api/catalog/edinitsy",
        "/api/catalog/firmy",
        "/api/catalog/sklady",
        "/api/catalog/kassy",
        "/api/catalog/kontragenty",
        "/api/catalog/dogovory",
        "/api/catalog/nomenklatura",
        "/api/catalog/tipy_tsen",
        "/api/catalog/constants",
    ):
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} вернул {resp.status_code}"


async def test_catalog_read_ok_for_admin(client, admin_headers):
    for path in (
        "/api/catalog/valyuty",
        "/api/catalog/nomenklatura",
        "/api/catalog/constants",
    ):
        resp = await client.get(path, headers=admin_headers)
        assert resp.status_code == 200, f"{path} вернул {resp.status_code}"


# --- Каталог: запись ---


async def test_catalog_write_requires_auth(client):
    for path, payload in (
        ("/api/catalog/valyuty", {"code": "XXX", "name": "Тест"}),
        ("/api/catalog/sklady", {"code": "99", "name": "Склад"}),
        ("/api/catalog/nomenklatura", {"name": "Товар"}),
    ):
        resp = await client.post(path, json=payload)
        assert resp.status_code == 401, f"{path} вернул {resp.status_code}"


async def test_catalog_write_ok_for_admin(client, admin_headers, seeded_session):
    resp = await client.post(
        "/api/catalog/sklady",
        json={"code": "99", "name": "Склад", "tip": "optovy"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text


# --- Отчёты: чтение ---


async def test_reports_require_auth(client):
    for path in (
        "/api/reports/stock/balances",
        "/api/reports/settlements",
        "/api/reports/money/balance",
    ):
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} вернул {resp.status_code}"


async def test_reports_ok_for_admin(client, admin_headers):
    resp = await client.get("/api/reports/stock/balances", headers=admin_headers)
    assert resp.status_code == 200, resp.text
