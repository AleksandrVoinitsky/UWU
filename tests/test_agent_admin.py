"""Тесты управления AI-агентом (админка).

Покрывают: сид дефолтных промптов/инструментов, конфигурацию, версионирование
промптов, инструменты, API-ключи (хеширование/верификация) и рендер страниц
админки. Одобрение (human-in-the-loop) полностью убрано.

См. также: :mod:`app.services.agent_service`, :mod:`app.web.agent_admin`,
:mod:`app.models.agent`.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.agent import AgentPrompt, AgentTool
from app.services import agent_service


# ---------------------------------------------------------------------------
# Сид
# ---------------------------------------------------------------------------
async def test_seed_agent_creates_defaults(seeded_session):
    prompts = await agent_service.list_prompts(seeded_session)
    keys = {p.key for p in prompts}
    assert {"system", "classify_intent", "generate", "reorder_suggestion"} <= keys

    tools = await agent_service.list_tools(seeded_session)
    tool_keys = {t.key for t in tools}
    assert {"search_catalog", "get_stock", "create_order"} <= tool_keys


async def test_seed_agent_is_idempotent(seeded_session):
    await agent_service.seed_agent(seeded_session)
    await agent_service.seed_agent(seeded_session)
    prompts = await agent_service.list_prompts(seeded_session)
    tools = await agent_service.list_tools(seeded_session)
    assert len([p for p in prompts if p.key == "system"]) == 1
    assert len([t for t in tools if t.key == "create_order"]) == 1


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
async def test_config_get_set(seeded_session):
    config = await agent_service.get_configs(seeded_session)
    assert config["fallback_message"]
    # Модель/параметры LLM в админке не управляются — они задаются env сервиса uwu-ai-agent.
    assert "model" not in config
    assert "temperature" not in config
    await agent_service.set_config(seeded_session, "fallback_message", "Оператор на связи.")
    config = await agent_service.get_configs(seeded_session)
    assert config["fallback_message"] == "Оператор на связи."


# ---------------------------------------------------------------------------
# Промпты и версии
# ---------------------------------------------------------------------------
async def test_prompt_versioning_and_rollback(seeded_session):
    system = next(p for p in await agent_service.list_prompts(seeded_session) if p.key == "system")
    assert system.active_version == 1

    await agent_service.add_prompt_version(
        seeded_session, system, "Новый системный промпт", variables=["customer"]
    )
    system = await agent_service.get_prompt(seeded_session, system.id)
    assert system.active_version == 2

    # Откат на v1.
    await agent_service.activate_prompt_version(seeded_session, system, 1)
    system = await agent_service.get_prompt(seeded_session, system.id)
    assert system.active_version == 1


async def test_activate_missing_version_raises(seeded_session):
    system = next(p for p in await agent_service.list_prompts(seeded_session) if p.key == "system")
    with pytest.raises(ValueError):
        await agent_service.activate_prompt_version(seeded_session, system, 999)


async def test_create_prompt(seeded_session):
    prompt = await agent_service.create_prompt(
        seeded_session,
        key="test_prompt",
        name="Тест",
        template="Привет {name}",
        variables=["name"],
    )
    assert prompt.active_version == 1
    loaded = next(p for p in await agent_service.list_prompts(seeded_session) if p.key == "test_prompt")
    assert len(loaded.versions) == 1


# ---------------------------------------------------------------------------
# Инструменты
# ---------------------------------------------------------------------------
async def test_update_tool(seeded_session):
    tool = next(t for t in await agent_service.list_tools(seeded_session) if t.key == "create_order")

    await agent_service.update_tool(
        seeded_session, tool, enabled=False, rate_limit=5
    )
    tool = await agent_service.get_tool(seeded_session, tool.id)
    assert tool.enabled is False
    assert tool.rate_limit == 5


async def test_default_tools_include_order_flow(seeded_session):
    """Сид создаёт инструменты сбора заказа и привязки по телефону."""
    tools = {t.key: t for t in await agent_service.list_tools(seeded_session)}
    assert "create_order" in tools
    assert "match_customer" in tools
    assert "search_catalog" in tools


# ---------------------------------------------------------------------------
# API-ключи
# ---------------------------------------------------------------------------
async def test_api_key_roundtrip(seeded_session):
    key, raw = await agent_service.create_key(seeded_session, "prod")
    assert raw.startswith("uwu_")
    assert len(raw) > 30

    verified = await agent_service.verify_key(seeded_session, raw)
    assert verified is not None and verified.id == key.id


async def test_api_key_disabled_rejects(seeded_session):
    key, raw = await agent_service.create_key(seeded_session, "prod")
    await agent_service.set_key_enabled(seeded_session, key, False)
    assert await agent_service.verify_key(seeded_session, raw) is None


async def test_api_key_wrong_raw_rejects(seeded_session):
    await agent_service.create_key(seeded_session, "prod")
    assert await agent_service.verify_key(seeded_session, "uwu_wrong") is None


# ---------------------------------------------------------------------------
# Маршруты админки
# ---------------------------------------------------------------------------
_AGENT_ROUTES = [
    "/admin/agent",
    "/admin/agent/prompts",
    "/admin/agent/tools",
    "/admin/agent/keys",
    "/admin/agent/runs",
]


@pytest.mark.parametrize("route", _AGENT_ROUTES)
async def test_agent_admin_routes_render(client, seeded_session, admin_token, route):
    client.cookies.set("access_token", admin_token)
    resp = await client.get(route)
    assert resp.status_code == 200, f"{route} failed: {resp.status_code}"


async def test_agent_admin_requires_admin(client, seeded_session):
    from app.models.users import Role
    from app.services import user_service
    from app.core.security import create_access_token

    role = (await seeded_session.execute(select(Role).where(Role.key == "operator"))).scalar_one()
    user = await user_service.create_user(
        seeded_session, login="agentop", password="secret123", role_id=role.id
    )
    client.cookies.set("access_token", create_access_token(str(user.id)))
    resp = await client.get("/admin/agent")
    assert resp.status_code == 303  # редирект на /


async def test_agent_overview_shows_sections(client, seeded_session, admin_token):
    client.cookies.set("access_token", admin_token)
    resp = await client.get("/admin/agent")
    assert resp.status_code == 200
    assert "Конфигурация агента" in resp.text
    assert "Промпты" in resp.text
    assert "Инструменты" in resp.text
    assert "API-ключи" in resp.text


async def test_create_key_via_route_shows_raw_once(client, seeded_session, admin_token):
    client.cookies.set("access_token", admin_token)
    resp = await client.post("/admin/agent/keys", data={"name": "test-key"})
    assert resp.status_code == 200
    assert "Новый ключ создан" in resp.text
    assert "uwu_" in resp.text
