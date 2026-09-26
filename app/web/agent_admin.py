"""Веб-интерфейс управления AI-агентом (админка).

Страницы: обзор/конфигурация, промпты (версионирование), инструменты, API-ключи,
журнал запусков и очередь одобрений (human-in-the-loop).

См. также: :mod:`app.services.agent_service`, :mod:`app.models.agent`.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user_from_cookie
from app.core.i18n import translate
from app.models.agent import APPROVAL_POLICIES, APPROVAL_STATUSES, AgentApiKey
from app.models.users import User
from app.services import agent_service
from app.templates import render

router = APIRouter(tags=["web-admin-agent"])


def _lang(request: Request) -> str:
    return request.cookies.get("lang") or "ru"


def _page(request: Request, user: User, template: str, **ctx) -> HTMLResponse:
    return HTMLResponse(
        render(
            template,
            lang=_lang(request),
            t=translate,
            user=user,
            section="admin",
            **ctx,
        )
    )


def _require_admin(user: User):
    return not user.is_admin


def _as_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        return None


def _as_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _as_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


# --- Обзор и конфигурация -----------------------------------------------------


@router.get("/admin/agent", response_class=HTMLResponse)
async def agent_overview(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    config = await agent_service.get_configs(session)
    prompts = await agent_service.list_prompts(session)
    tools = await agent_service.list_tools(session)
    keys = await agent_service.list_keys(session)
    pending = await agent_service.list_approvals(session, status="pending", limit=20)
    runs = await agent_service.list_runs(session, limit=10)
    return _page(
        request,
        user,
        "admin/agent.html",
        config=config,
        prompts=prompts,
        tools=tools,
        keys=keys,
        pending=pending,
        runs=runs,
    )


@router.post("/admin/agent/config", response_class=HTMLResponse)
async def agent_save_config(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    await agent_service.set_configs(session, {k: str(v) for k, v in form.items()})
    return RedirectResponse("/admin/agent", status_code=303)


# --- Промпты ------------------------------------------------------------------


@router.get("/admin/agent/prompts", response_class=HTMLResponse)
async def agent_prompts(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    prompts = await agent_service.list_prompts(session)
    return _page(request, user, "admin/agent_prompts.html", prompts=prompts)


@router.post("/admin/agent/prompts", response_class=HTMLResponse)
async def agent_create_prompt(
    request: Request,
    key: str = Form(...),
    name: str = Form(...),
    template: str = Form(...),
    description: str = Form(""),
    variables: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    key = (key or "").strip()
    if key:
        await agent_service.create_prompt(
            session,
            key=key,
            name=name or key,
            template=template,
            description=description or None,
            variables=[v.strip() for v in variables.split(",") if v.strip()],
            updated_by=user.login,
        )
    return RedirectResponse("/admin/agent/prompts", status_code=303)


@router.post("/admin/agent/prompts/{prompt_id}/version", response_class=HTMLResponse)
async def agent_add_prompt_version(
    prompt_id: int,
    request: Request,
    template: str = Form(...),
    variables: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    max_tokens: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    prompt = await agent_service.get_prompt(session, prompt_id)
    if prompt:
        await agent_service.add_prompt_version(
            session,
            prompt,
            template=template,
            variables=[v.strip() for v in variables.split(",") if v.strip()],
            model=model or None,
            temperature=_as_float(temperature),
            max_tokens=_as_int(max_tokens),
            updated_by=user.login,
        )
    return RedirectResponse("/admin/agent/prompts", status_code=303)


@router.post("/admin/agent/prompts/{prompt_id}/activate", response_class=HTMLResponse)
async def agent_activate_prompt_version(
    prompt_id: int,
    version: int = Form(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    prompt = await agent_service.get_prompt(session, prompt_id)
    if prompt:
        try:
            await agent_service.activate_prompt_version(session, prompt, version)
        except ValueError:
            pass
    return RedirectResponse("/admin/agent/prompts", status_code=303)


# --- Инструменты --------------------------------------------------------------


@router.get("/admin/agent/tools", response_class=HTMLResponse)
async def agent_tools(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    tools = await agent_service.list_tools(session)
    return _page(
        request,
        user,
        "admin/agent_tools.html",
        tools=tools,
        policies=APPROVAL_POLICIES,
    )


@router.post("/admin/agent/tools/{tool_id}", response_class=HTMLResponse)
async def agent_update_tool(
    tool_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    endpoint: str = Form(...),
    method: str = Form(...),
    permission: str = Form(""),
    approval_policy: str = Form("auto"),
    approval_threshold_amount: str = Form(""),
    rate_limit: str = Form("60"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    tool = await agent_service.get_tool(session, tool_id)
    if tool:
        form = await request.form()
        await agent_service.update_tool(
            session,
            tool,
            name=name,
            description=description,
            endpoint=endpoint,
            method=method.upper() or "GET",
            permission=permission or None,
            approval_policy=approval_policy,
            approval_threshold_amount=_as_decimal(approval_threshold_amount),
            enabled=form.get("enabled") == "on",
            rate_limit=_as_int(rate_limit) or 60,
        )
    return RedirectResponse("/admin/agent/tools", status_code=303)


# --- API-ключи ----------------------------------------------------------------


@router.get("/admin/agent/keys", response_class=HTMLResponse)
async def agent_keys(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    keys = await agent_service.list_keys(session)
    return _page(request, user, "admin/agent_keys.html", keys=keys, new_key=None, new_key_name=None)


@router.post("/admin/agent/keys", response_class=HTMLResponse)
async def agent_create_key(
    request: Request,
    name: str = Form(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    key, raw = await agent_service.create_key(session, name=name or "API-ключ")
    keys = await agent_service.list_keys(session)
    return _page(
        request,
        user,
        "admin/agent_keys.html",
        keys=keys,
        new_key=raw,
        new_key_name=name or "API-ключ",
    )


@router.post("/admin/agent/keys/{key_id}/toggle", response_class=HTMLResponse)
async def agent_toggle_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    key = await session.get(AgentApiKey, key_id)
    if key:
        await agent_service.set_key_enabled(session, key, not key.enabled)
    return RedirectResponse("/admin/agent/keys", status_code=303)


@router.post("/admin/agent/keys/{key_id}/delete", response_class=HTMLResponse)
async def agent_delete_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    key = await session.get(AgentApiKey, key_id)
    if key:
        await agent_service.delete_key(session, key)
    return RedirectResponse("/admin/agent/keys", status_code=303)


# --- Журнал запусков и одобрения ----------------------------------------------


@router.get("/admin/agent/runs", response_class=HTMLResponse)
async def agent_runs(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    runs = await agent_service.list_runs(session)
    return _page(request, user, "admin/agent_runs.html", runs=runs)


@router.get("/admin/agent/approvals", response_class=HTMLResponse)
async def agent_approvals(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    approvals = await agent_service.list_approvals(session)
    return _page(
        request,
        user,
        "admin/agent_approvals.html",
        approvals=approvals,
        statuses=APPROVAL_STATUSES,
    )


@router.post("/admin/agent/approvals/{approval_id}/decide", response_class=HTMLResponse)
async def agent_decide_approval(
    approval_id: int,
    approve: str = Form(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if _require_admin(user):
        return RedirectResponse("/", status_code=303)
    approval = await agent_service.get_approval(session, approval_id)
    if approval and approval.status == "pending":
        await agent_service.decide_approval(
            session, approval, approve=approve == "approve", decided_by=user.login
        )
    return RedirectResponse("/admin/agent/approvals", status_code=303)
