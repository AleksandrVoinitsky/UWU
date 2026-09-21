"""Тесты аутентификации.

См. также: :mod:`app.services.auth_service`, :mod:`app.api.auth`.
"""
from __future__ import annotations

from app.core.config import settings


async def test_login_success(client, seeded_session):
    resp = await client.post(
        "/api/auth/login",
        json={"login": settings.admin_login, "password": settings.admin_password},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client, seeded_session):
    resp = await client.post(
        "/api/auth/login",
        json={"login": settings.admin_login, "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(client, seeded_session):
    resp = await client.post(
        "/api/auth/login", json={"login": "nobody", "password": "whatever"}
    )
    assert resp.status_code == 401
