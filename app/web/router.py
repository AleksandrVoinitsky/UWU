"""Агрегирующий роутер веб-интерфейса."""
from fastapi import APIRouter

from app.web import auth, admin, trade, docs, agent_admin, site_admin

web_router = APIRouter()
web_router.include_router(auth.router)
web_router.include_router(admin.router)
web_router.include_router(agent_admin.router)
web_router.include_router(site_admin.router)
web_router.include_router(trade.router)
web_router.include_router(docs.router)
