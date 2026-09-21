"""Тесты управления пользователями (админ).

См. также: :mod:`app.services.user_service`, :mod:`app.api.users`.
"""
from __future__ import annotations

from app.services import user_service


async def test_seed_creates_admin(seeded_session):
    users = await user_service.list_users(seeded_session)
    admins = [u for u in users if u.is_admin]
    assert len(admins) == 1


async def test_seed_creates_default_roles(seeded_session):
    roles = await user_service.list_roles(seeded_session)
    keys = {r.key for r in roles}
    assert {"admin", "operator", "accountant"} <= keys


async def test_create_user_via_api(client, admin_headers):
    resp = await client.post(
        "/api/users",
        json={"login": "operator1", "password": "pass1234", "full_name": "Оператор"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["login"] == "operator1"


async def test_create_duplicate_login_conflict(client, admin_headers):
    payload = {"login": "dup", "password": "pass1234"}
    r1 = await client.post("/api/users", json=payload, headers=admin_headers)
    assert r1.status_code == 201
    r2 = await client.post("/api/users", json=payload, headers=admin_headers)
    assert r2.status_code == 409


async def test_list_users_requires_admin(client, admin_headers):
    resp = await client.get("/api/users")
    assert resp.status_code == 401  # без токена


async def test_cannot_delete_admin(client, admin_headers, seeded_session):
    users = await user_service.list_users(seeded_session)
    admin = next(u for u in users if u.is_admin)
    resp = await client.delete(f"/api/users/{admin.id}", headers=admin_headers)
    assert resp.status_code == 400
