"""Тесты справочников (НСИ).

См. также: :mod:`app.services.catalog_service`, :mod:`app.api.catalog`.
"""
from __future__ import annotations

from app.services import catalog_service
from app.models.catalog import Kontragent, Nomenklatura


async def test_nomenklatura_auto_code(seeded_session):
    first = await catalog_service.create_one(
        seeded_session, Nomenklatura, code="", name="Товар 1"
    )
    assert first.id
    # Автогенерация кода
    code = await catalog_service.next_nomenklatura_code(seeded_session)
    assert code == "001"


async def test_kontragent_auto_code(seeded_session):
    await catalog_service.create_one(seeded_session, Kontragent, code="001", name="Клиент")
    code = await catalog_service.next_kontragent_code(seeded_session)
    assert code == "002"


async def test_create_nomenklatura_via_api(client, admin_headers):
    resp = await client.post(
        "/api/catalog/nomenklatura",
        json={"code": "", "name": "Телевизор", "vid": "tovar"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Телевизор"
    assert data["code"] == "001"


async def test_list_valyuty_seeded(client, admin_headers, seeded_session):
    resp = await client.get("/api/catalog/valyuty", headers=admin_headers)
    assert resp.status_code == 200
    codes = {v["code"] for v in resp.json()}
    assert "RUB" in codes
