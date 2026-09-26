"""Тесты фронтенда: иконки, макросы, дизайн-система, тема, дашборды.

Проверяют переиспользуемые компоненты (иконки и Jinja-макросы), наличие
тёмной темы, переработанные дашборды и что каталоги рендерятся через общую
библиотеку ``_components.html``.

См. также: :mod:`app.web.icons`, :mod:`app.templates`,
:mod:`app.templates._components`.
"""
from __future__ import annotations

import pytest
from markupsafe import Markup
from sqlalchemy import select

from app.core.i18n import translate
from app.core.security import create_access_token
from app.models.users import Role
from app.services import user_service
from app.web.icons import ICONS, icon


# ---------------------------------------------------------------------------
# Иконки
# ---------------------------------------------------------------------------
def test_icon_returns_svg_markup():
    out = icon("search")
    assert isinstance(out, Markup)
    assert "<svg" in str(out)
    assert 'viewBox="0 0 24 24"' in str(out)
    assert 'stroke="currentColor"' in str(out)


def test_icon_unknown_name_returns_empty():
    assert str(icon("this-icon-does-not-exist")) == ""


def test_all_icons_render_non_empty_svg():
    for name in ICONS:
        assert "<svg" in str(icon(name)), f"icon {name!r} is empty"


def test_icon_accepts_size_and_class():
    out = str(icon("plus", size=24, cls="qa-icon"))
    assert 'width="24"' in out
    assert 'class="ico qa-icon"' in out


# ---------------------------------------------------------------------------
# i18n новых ключей
# ---------------------------------------------------------------------------
def test_new_i18n_keys_present_in_both_languages():
    assert translate("common.theme", "ru") == "Переключить тему"
    assert translate("common.theme", "en") == "Toggle theme"
    assert translate("common.empty", "ru") == "Нет записей"
    assert translate("common.empty", "en") == "No records"
    assert translate("admin.active_users", "ru") == "Активные"
    assert translate("admin.active_users", "en") == "Active"


# ---------------------------------------------------------------------------
# Вспомогательная фикстура: пользователь-оператор
# ---------------------------------------------------------------------------
async def _operator(client, seeded_session, login: str):
    role = (
        await seeded_session.execute(select(Role).where(Role.key == "operator"))
    ).scalar_one()
    user = await user_service.create_user(
        seeded_session, login=login, password="secret123", role_id=role.id
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))
    return user


# ---------------------------------------------------------------------------
# Маршруты и дизайн-система
# ---------------------------------------------------------------------------
async def test_login_page_has_theme_toggle(client):
    resp = await client.get("/login")
    assert resp.status_code == 200
    assert "theme-toggle" in resp.text
    assert "brand-mark" in resp.text


async def test_dashboard_uses_design_system(client, seeded_session):
    await _operator(client, seeded_session, "dsop")
    resp = await client.get("/")
    assert resp.status_code == 200
    # Герой-блок и анимированные счётчики.
    assert "dash-hero" in resp.text
    assert "data-counter" in resp.text
    # SVG-иконки (inline) присутствуют в навигации.
    assert '<svg class="ico' in resp.text


async def test_catalog_uses_shared_macros(client, seeded_session):
    await _operator(client, seeded_session, "catop")
    resp = await client.get("/catalog/kontragenty")
    assert resp.status_code == 200
    # Поиск и модальное окно рендерятся через макросы.
    assert 'data-search="#kg-table"' in resp.text
    assert 'role="dialog"' in resp.text
    assert "modal-footer" in resp.text


# Все справочники должны рендериться через общую библиотеку макросов
# (проверяет рефакторинг шаблонов и отсутствие регрессий рендера).
_CATALOG_ROUTES = [
    "/catalog/nomenklatura",
    "/catalog/kontragenty",
    "/dogovory",
    "/catalog/sklady",
    "/catalog/firmy",
    "/catalog/kassy",
    "/catalog/valyuty",
    "/catalog/edinitsy",
    "/catalog/stavki_nds",
    "/catalog/tipy_tsen",
    "/catalog/categories",
    "/catalog/sotrudniki",
    "/catalog/scheta",
]


@pytest.mark.parametrize("route", _CATALOG_ROUTES)
async def test_catalog_routes_render_with_macros(client, seeded_session, route):
    await _operator(client, seeded_session, "catalogsmoke")
    resp = await client.get(route)
    assert resp.status_code == 200, f"{route} failed: {resp.status_code}"
    assert "search-input" in resp.text, f"{route}: no search-input macro"
    assert "modal-footer" in resp.text, f"{route}: no modal-footer macro"


async def test_admin_dashboard_has_kpi_cards(client, seeded_session, admin_token):
    client.cookies.set("access_token", admin_token)
    resp = await client.get("/admin")
    assert resp.status_code == 200
    assert "kpi-card" in resp.text
    assert "quick-actions" in resp.text


async def test_theme_toggle_script_loaded(client):
    """app.js содержит обработчик переключения темы."""
    resp = await client.get("/static/js/app.js")
    assert resp.status_code == 200
    assert "theme-toggle" in resp.text
    assert "uwu-theme" in resp.text


async def test_css_has_dark_mode_tokens(client):
    resp = await client.get("/static/css/style.css")
    assert resp.status_code == 200
    assert 'data-theme="dark"' in resp.text
    assert "prefers-reduced-motion" in resp.text
    assert "backdrop-filter" in resp.text
