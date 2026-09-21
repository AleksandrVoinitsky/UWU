"""Встроенная документация (Markdown) в админке.

Документация хранится в ``docs/`` и рендерится в админ-интерфейсе. Это
единственный источник правды для описания функций.

См. также: :mod:`app.services.user_service`, ``docs/``.
"""
from __future__ import annotations

import re
from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user_from_cookie
from app.core.i18n import translate
from app.models.users import User
from app.templates import render

router = APIRouter(tags=["web-docs"])

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"


def _load_doc(name: str) -> str | None:
    """Загружает Markdown-файл документации по имени (без расширения)."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", name)
    path = DOCS_DIR / f"{safe}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _render_md(text: str) -> str:
    return markdown.markdown(text, extensions=["toc", "tables", "fenced_code"])


@router.get("/admin/docs", response_class=HTMLResponse)
async def docs_index(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    files = sorted(p.stem for p in DOCS_DIR.glob("*.md"))
    content = _load_doc("README") or _load_doc("index") or ""
    return HTMLResponse(
        render(
            "admin/docs.html",
            lang=request.cookies.get("lang") or "ru",
            t=translate,
            user=user,
            section="admin",
            files=files,
            current="index",
            content=_render_md(content),
        )
    )


@router.get("/admin/docs/{name}", response_class=HTMLResponse)
async def docs_page(
    name: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_from_cookie),
):
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    raw = _load_doc(name)
    if raw is None:
        return HTMLResponse("Not found", status_code=404)
    files = sorted(p.stem for p in DOCS_DIR.glob("*.md"))
    return HTMLResponse(
        render(
            "admin/docs.html",
            lang=request.cookies.get("lang") or "ru",
            t=translate,
            user=user,
            section="admin",
            files=files,
            current=name,
            content=_render_md(raw),
        )
    )
